"""Append-only, hash-chained summaries of verified playtest runs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .transcript import ZERO_HASH, canonical_json

LEDGER_VERSION = 1
RUN_OUTCOMES = {"COMPLETE", "INCOMPLETE_DISPATCH", "BLINDNESS_VIOLATED", "AUDIT_UNVERIFIABLE", "ERROR"}


def _entry_hash(entry):
    body = {key: value for key, value in entry.items() if key != "entry_hash"}
    return hashlib.sha256((entry["prev_hash"] + canonical_json(body)).encode("utf-8")).hexdigest()


def verify_ledger(path):
    path = Path(path)
    entries, previous = [], ZERO_HASH
    if not path.exists():
        raise ValueError("ledger is missing")
    with path.open("r", encoding="utf-8", newline="") as source:
        for number, line in enumerate(source, 1):
            if not line.endswith("\n"):
                raise ValueError(f"ledger line {number} is incomplete")
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid ledger line {number}") from exc
            if canonical_json(entry) + "\n" != line:
                raise ValueError(f"noncanonical ledger line {number}")
            if entry.get("prev_hash") != previous or entry.get("entry_hash") != _entry_hash(entry):
                raise ValueError(f"ledger chain mismatch at line {number}")
            previous = entry["entry_hash"]
            entries.append(entry)
    anchor_path = path.with_name(path.name + ".head")
    try:
        anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("ledger head anchor is missing or invalid") from exc
    if anchor != {"record_count": len(entries), "chain_hash": previous}:
        raise ValueError("ledger head anchor mismatch (ledger may be truncated or altered)")
    return entries


def make_entry(*, run_id, game_sha, harness_sha, detector_version, persona_id, seed,
               is_holdout=False, holdout_prompt_sha256=None, narrator_policy="plain", turn_cap=35,
               golem_model=None, golem_effort=None, judge_version=None, judge_model=None,
               judge_effort=None, transcript_head_chain_hash=None, run_outcome="COMPLETE",
               termination=None, turns=0, instances=(), judge_instances=(), curiosity=None,
               coverage=None, discarded_judge_claims=0, unsupported_intents=(),
               eligibility_flags=None, **extra):
    """Build an entry from verified facts. Holdout prompt content is never accepted/stored."""
    if run_outcome not in RUN_OUTCOMES:
        raise ValueError("invalid run_outcome")
    if type(is_holdout) is not bool:
        raise ValueError("is_holdout must be bool")
    if is_holdout and holdout_prompt_sha256 is not None and (len(holdout_prompt_sha256) != 64 or any(c not in "0123456789abcdef" for c in holdout_prompt_sha256)):
        raise ValueError("holdout_prompt_sha256 must be a lowercase SHA-256 digest or null")
    counts = {"detector": {}, "judge": {}}
    weighted = {"detector": {}, "judge": {}}
    for source, values in (("detector", instances), ("judge", judge_instances)):
        for item in values:
            if not item.get("verified", source == "detector"):
                continue
            mode = item["mode"]
            counts[source][mode] = counts[source].get(mode, 0) + 1
            weighted[source][mode] = weighted[source].get(mode, 0) + int(item.get("severity", 0))
    cov = dict(coverage or {})
    facts = dict(eligibility_flags or {})
    eligible = run_outcome == "COMPLETE"
    reason = None if eligible else "RUN_OUTCOME_" + run_outcome
    facts.update(comparison_eligible=eligible, reason_code=reason)
    return {"ledger_version": LEDGER_VERSION, "run_id": run_id, "game_sha": game_sha,
            "harness_sha": harness_sha, "detector_version": detector_version,
            "judge_version": judge_version, "persona_id": persona_id, "seed": seed,
            "is_holdout": is_holdout,
            "holdout_prompt_sha256": holdout_prompt_sha256 if is_holdout else None,
            "narrator_policy": narrator_policy, "turn_cap": turn_cap,
            "golem": {"model": golem_model, "effort": golem_effort},
            "judge": {"model": judge_model, "effort": judge_effort},
            "transcript_head_chain_hash": transcript_head_chain_hash,
            "run_outcome": run_outcome, "termination": termination, "turns": turns,
            "per_mode_verified_instances": counts, "severity_weighted_counts": weighted,
            "curiosity": dict(curiosity or {}),
            "coverage": {"rooms_visited": int(cov.get("rooms_visited", 0)),
                         "objects_touched": int(cov.get("objects_touched", cov.get("distinct_object_names_touched", 0))),
                         "encounters_faced": int(cov.get("encounters_faced", 0))},
            "discarded_judge_claims": int(discarded_judge_claims),
            "unsupported_intents": list(unsupported_intents), "eligibility": facts}


def append_entry(path, entry):
    path = Path(path)
    if not path.exists() and path.with_name(path.name + ".head").exists():
        raise ValueError("ledger data is missing while its head anchor exists")
    entries = verify_ledger(path) if path.exists() else []
    previous = entries[-1]["entry_hash"] if entries else ZERO_HASH
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
