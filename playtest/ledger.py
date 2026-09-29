"""Append-only, hash-chained summaries of verified playtest runs.

The local .head anchor detects partial edits, deletion, and truncation. It is not
an identity proof: a writer able to rewrite both ledger and anchor can forge a
new internally consistent history. Record :func:`head_hash` in an independently
protected receipt (for example, a committed evidence file) to detect that case.
This design does not defend against an attacker able to rewrite that external
anchor too.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .schema import (SCHEMA_VERSION, SEVERITY_TAXONOMY_VERSION, canonical_json, catalog_digest,
                     GAME_ENTRYPOINTS, GAME_TREE_SPECS, normalize_instance, strict_json_loads, validate_ledger_entry)
from .transcript import ZERO_HASH

LEDGER_VERSION = 2
RUN_OUTCOMES = {"COMPLETE", "INCOMPLETE_DISPATCH", "BLINDNESS_VIOLATED", "AUDIT_UNVERIFIABLE", "GAME_MODIFIED_DURING_RUN", "ERROR"}


class LegacyLedgerRecords(list):
    legacy = True
    eligible = False


def _entry_hash(entry):
    body = {key: value for key, value in entry.items() if key != "entry_hash"}
    return hashlib.sha256((entry["prev_hash"] + canonical_json(body)).encode("utf-8")).hexdigest()


def head_hash(path):
    """Return the current locally anchored chain hash (ZERO_HASH for empty)."""
    path = Path(path)
    if not path.exists():
        raise ValueError("ledger is missing")
    entries = verify_ledger(path)
    return entries[-1]["entry_hash"] if entries else ZERO_HASH


def verify_ledger(path, expected_head=None):
    path = Path(path)
    entries, previous, legacy = [], ZERO_HASH, False
    if not path.exists():
        raise ValueError("ledger is missing")
    with path.open("r", encoding="utf-8", newline="") as source:
        for number, line in enumerate(source, 1):
            if not line.endswith("\n"):
                raise ValueError(f"ledger line {number} is incomplete")
            try:
                entry = strict_json_loads(line)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"invalid ledger line {number}") from exc
            if canonical_json(entry) + "\n" != line:
                raise ValueError(f"noncanonical ledger line {number}")
            if entry.get("schema_version") == 2:
                validate_ledger_entry({key: value for key, value in entry.items() if key not in {"prev_hash", "entry_hash"}})
            else:
                legacy = True
            if entry.get("prev_hash") != previous or entry.get("entry_hash") != _entry_hash(entry):
                raise ValueError(f"ledger chain mismatch at line {number}")
            previous = entry["entry_hash"]
            entries.append(entry)
    anchor_path = path.with_name(path.name + ".head")
    try:
        anchor = strict_json_loads(anchor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("ledger head anchor is missing or invalid") from exc
    if anchor != {"record_count": len(entries), "chain_hash": previous}:
        raise ValueError("ledger head anchor mismatch (ledger may be truncated or altered)")
    if expected_head is not None and expected_head != previous:
        raise ValueError("ledger expected head mismatch")
    return LegacyLedgerRecords(entries) if legacy else entries


def make_entry(*, run_id, game_sha, harness_sha, detector_version, persona_id, seed,
               session_id, manifest_sha256, run_receipt_sha256, journal_sha256,
               transcript_head_chain_hash, persona_prompt_sha256, content_catalog,
               is_holdout=False, holdout_prompt_sha256=None, narrator_policy="plain",
               turn_policy="action_frames_v1", turn_cap=35,
               severity_taxonomy_version=SEVERITY_TAXONOMY_VERSION,
               measurement_policy="detector_only", golem_model=None, golem_effort=None,
               judge_version=None, verifier_version=None, judge_model=None, judge_effort=None,
               game_revision=None, harness_revision=None, judge_receipt_sha256=None,
               judge_status=None, termination=None, run_outcome="COMPLETE", turns=0,
               transcript_record_count=None, verified_instances=(), curiosity=None,
               coverage=None, discarded_judge_claims=None, eligibility_flags=None,
               expected_content_change=None, game_id="dnd_combat", schema_minor=1,
               detector_set_status="IMPLEMENTED"):
    """Build from already validated and normalized artifact facts only."""
    if run_outcome not in RUN_OUTCOMES: raise ValueError("invalid run_outcome")
    if type(is_holdout) is not bool: raise ValueError("is_holdout must be bool")
    if is_holdout and holdout_prompt_sha256 != persona_prompt_sha256: raise ValueError("holdout prompt identity mismatch")
    if not is_holdout and holdout_prompt_sha256 is not None: raise ValueError("public run must have null holdout identity")
    digest_values = {"game_sha": game_sha, "harness_sha": harness_sha,
        "manifest_sha256": manifest_sha256, "run_receipt_sha256": run_receipt_sha256,
        "journal_sha256": journal_sha256, "transcript_head_chain_hash": transcript_head_chain_hash,
        "persona_prompt_sha256": persona_prompt_sha256}
    for label, value in digest_values.items():
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    if type(seed) is not int: raise ValueError("seed must be an integer")
    if game_id not in GAME_ENTRYPOINTS: raise ValueError("unsupported game_id")
    if detector_set_status not in {"IMPLEMENTED", "NOT_IMPLEMENTED"}: raise ValueError("invalid detector_set_status")
    if type(turns) is not int or turns < 0: raise ValueError("turns must be nonnegative action frames")
    normalized = list(verified_instances)
    for item in normalized:
        from .schema import validate_verified_instance
        validate_verified_instance(item)
    if judge_status is None:
        judge_status = "NOT_REQUESTED" if measurement_policy == "detector_only" else "INCOMPLETE"
    if judge_status not in {"NOT_REQUESTED", "COMPLETE", "INCOMPLETE", "INVALID"}:
        raise ValueError("invalid judge_status")
    counts = {"detector": {}, "judge": None if judge_status == "NOT_REQUESTED" else {}}
    weighted = {"detector": {}, "judge": None if counts["judge"] is None else {}}
    for item in normalized:
        source, mode, severity = item["source"], item["mode"], item["severity"]
        if counts[source] is None: raise ValueError("judge instance present when judge was not requested")
        counts[source][mode] = counts[source].get(mode, 0) + 1
        weighted[source][mode] = weighted[source].get(mode, 0) + severity
    cov = dict(coverage or {})
    facts = dict(eligibility_flags or {})
    identity_present = all((run_id, session_id, game_sha, harness_sha, persona_id,
        persona_prompt_sha256, seed is not None, turn_cap, narrator_policy, turn_policy,
        measurement_policy, detector_version))
    eligible = run_outcome == "COMPLETE" and turns > 0 and identity_present and judge_status in {"NOT_REQUESTED", "COMPLETE"}
    reason = None if eligible else ("RUN_OUTCOME_" + run_outcome if run_outcome != "COMPLETE" else
        "ZERO_ACTION_TURNS" if turns == 0 else "MISSING_PAIR_IDENTITY" if not identity_present else
        "JUDGE_" + judge_status if judge_status not in {"NOT_REQUESTED", "COMPLETE"} else "INELIGIBLE")
    if facts.get("comparison_eligible") is False: eligible, reason = False, facts.get("reason_code") or "INELIGIBLE"
    if detector_set_status == "NOT_IMPLEMENTED": eligible, reason = False, "DETECTORS_NOT_IMPLEMENTED_FOR_GAME"
    facts.update(comparison_eligible=eligible, reason_code=reason)
    if content_catalog is None: raise ValueError("content catalog is required")
    entry = {"schema_version": SCHEMA_VERSION, "schema_minor": schema_minor,
        "game_id": game_id, "game_entrypoint": GAME_ENTRYPOINTS[game_id],
        "game_tree_spec": GAME_TREE_SPECS[game_id], "detector_set_status": detector_set_status,
        "run_id": run_id, "session_id": session_id,
        "manifest_sha256": manifest_sha256, "run_receipt_sha256": run_receipt_sha256,
        "transcript_head_chain_hash": transcript_head_chain_hash, "journal_sha256": journal_sha256,
        "game_revision": game_revision, "harness_revision": harness_revision,
        "game_sha": game_sha, "harness_sha": harness_sha,
        "persona_id": persona_id, "persona_prompt_sha256": persona_prompt_sha256,
        "seed": seed, "is_holdout": is_holdout, "holdout_prompt_sha256": holdout_prompt_sha256,
        "narrator_policy": narrator_policy, "turn_policy": turn_policy, "turn_cap": turn_cap,
        "measurement_policy": measurement_policy, "severity_taxonomy_version": severity_taxonomy_version,
        "detector_version": detector_version,
        "turns": turns, "transcript_record_count": transcript_record_count if transcript_record_count is not None else turns + 1,
        "termination": termination, "run_outcome": run_outcome,
        "golem": {"model": golem_model, "effort": golem_effort},
        "judge_receipt_sha256": judge_receipt_sha256, "judge_status": judge_status,
        "judge_version": judge_version, "verifier_version": verifier_version,
        "judge_model": judge_model, "judge_effort": judge_effort,
        "judge_counted_instances": sum(item["source"] == "judge" for item in normalized) if judge_status == "COMPLETE" else None,
        "discarded_judge_claims": discarded_judge_claims if judge_status != "NOT_REQUESTED" else None,
        "per_mode_verified_instances": counts, "severity_weighted_counts": weighted,
        "verified_instances": normalized, "content_catalog": content_catalog,
        "catalog_sha256": catalog_digest(content_catalog),
        "coverage": {"rooms_visited": int(cov.get("rooms_visited", 0)),
                     "objects_touched": int(cov.get("objects_touched", 0)), "encounters_faced": int(cov.get("encounters_faced", 0))},
        "curiosity": dict(curiosity or {}), "expected_content_change": expected_content_change,
        "eligibility": facts}
    validate_ledger_entry(entry)
    return entry

def append_entry(path, entry):
    path = Path(path)
    if not path.exists() and path.with_name(path.name + ".head").exists():
        raise ValueError("ledger data is missing while its head anchor exists")
    entries = verify_ledger(path) if path.exists() else []
    if getattr(entries, "legacy", False): raise ValueError("cannot append v2 entries to a legacy ledger chain")
    previous = entries[-1]["entry_hash"] if entries else ZERO_HASH
    validate_ledger_entry(entry)
    stored = dict(entry, prev_hash=previous, entry_hash="0" * 64)
    stored["entry_hash"] = _entry_hash(stored)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as target:
        target.write(canonical_json(stored) + "\n"); target.flush(); os.fsync(target.fileno())
    anchor_path = path.with_name(path.name + ".head")
    temporary = anchor_path.with_name(anchor_path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as target:
        target.write(canonical_json({"record_count": len(entries) + 1, "chain_hash": stored["entry_hash"]}) + "\n")
        target.flush(); os.fsync(target.fileno())
    os.replace(temporary, anchor_path)
    return stored
