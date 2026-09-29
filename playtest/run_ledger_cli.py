"""Validate finalized artifacts and append a normalized v2 ledger entry."""
import argparse
import hashlib
import json
from pathlib import Path

from .detectors import DETECTOR_VERSION, curiosity_events, run_all, session_facts, verify_instance_quotes
from .golem_runner import validate_journal
from .judge import build_judge_bundle, build_judge_prompt
from .ledger import append_entry, make_entry
from .schema import (LegacyArtifact, canonical_json, catalog_digest, count_turns,
                     load_judge_receipt, load_manifest, load_run_receipt,
                     normalize_instance, source_digest, strict_json_loads)
from .transcript import load_transcript


def _sha(data): return hashlib.sha256(data).hexdigest()


def _rows(path):
    if not path.exists(): return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try: row = strict_json_loads(line)
        except (ValueError, json.JSONDecodeError) as exc: raise ValueError(f"invalid journal line {number}") from exc
        validate_journal(row); rows.append(row)
    return rows


def _evidence_sha(records, turn_ids):
    selected = [row for row in records if row["turn_id"] in set(turn_ids)]
    return _sha(canonical_json(selected).encode("utf-8"))


def _normalize_detectors(records, instances, run_dir):
    normalized = []
    probe_artifacts = []
    for item in instances:
        turns = item.get("turn_ids", [])
        if turns:
            evidence_sha = _evidence_sha(records, turns); kind = "transcript"
        else:
            artifact = item.get("probe_artifact")
            if not isinstance(artifact, dict): raise ValueError("static detector result lacks a probe artifact")
            probe_artifacts.append(artifact)
            evidence_sha = _sha(canonical_json(artifact).encode("utf-8")); kind = "static_probe"
        normalized.append(normalize_instance(source="detector", mode=item["mode"], turn_ids=turns,
            quote=item.get("quote", ""), rationale=item.get("rationale", ""), evidence_kind=kind,
            evidence_sha256=evidence_sha))
    probe_artifact = {"schema_version": 1, "detector_version": DETECTOR_VERSION,
                      "probes": probe_artifacts}
    probe_path = Path(run_dir) / "static_probe_evidence.json"
    probe_path.write_text(canonical_json(probe_artifact) + "\n", encoding="utf-8")
    recorded = {_sha(canonical_json(artifact).encode("utf-8")) for artifact in probe_artifact["probes"]}
    for item in normalized:
        if item["evidence_kind"] == "static_probe" and item["evidence_sha256"] not in recorded:
            raise ValueError("static detector evidence is not bound to a probe artifact")
    return normalized


def _verify_receipt_binding(receipt, manifest, records, journal_sha, run, journal):
    mismatch = []
    identities = (
        ("game_id", receipt.get("game_id", "dnd_combat"), manifest.get("game_id", "dnd_combat")),
        ("run_id", receipt["run_id"], manifest["run_id"]),
        ("session_id", receipt["session_id"], manifest["session_id"]),
        ("manifest_sha256", receipt["manifest_sha256"], manifest["manifest_sha256"]),
        ("game_sha", receipt["game_sha"], manifest["game_sha"]),
        ("harness_sha", receipt["harness_sha"], manifest["harness_sha"]),
        ("game_sha_end", receipt["game_sha_end"], manifest["game_sha"]),
        ("harness_sha_end", receipt["harness_sha_end"], manifest["harness_sha"]),
        ("game_revision", receipt["game_revision"], manifest["game_revision"]),
        ("harness_revision", receipt["harness_revision"], manifest["harness_revision"]),
        ("persona_id", receipt["persona_id"], manifest["persona_id"]),
        ("persona_prompt_sha256", receipt["persona_prompt_sha256"], manifest["persona_prompt_sha256"]),
        ("seed", receipt["seed"], manifest["seed"]),
        ("is_holdout", receipt["is_holdout"], manifest["is_holdout"]),
        ("holdout_prompt_sha256", receipt["holdout_prompt_sha256"], manifest["holdout_prompt_sha256"]),
        ("turn_cap", receipt["turn_cap"], manifest["turn_cap"]),
        ("turn_policy", receipt["turn_policy"], manifest["turn_policy"]),
        ("narrator_policy", receipt["narrator_policy"], manifest["narrator_policy"]),
        ("measurement_policy", receipt["measurement_policy"], manifest["measurement_policy"]),
        ("severity_taxonomy_version", receipt["severity_taxonomy_version"], manifest["severity_taxonomy_version"]),
    )
    mismatch.extend(name for name, actual, expected in identities if actual != expected)
    game_id = manifest.get("game_id", "dnd_combat")
    if receipt["game_files_start"] != manifest["game_files"] or source_digest("game", receipt["game_files_start"], game_id) != receipt["game_sha"]: mismatch.append("game_files")
    if receipt["harness_files_start"] != manifest["harness_files"] or source_digest("harness", receipt["harness_files_start"]) != receipt["harness_sha"]: mismatch.append("harness_files")
    if receipt["game_files_end"] != manifest["game_files"] or source_digest("game", receipt["game_files_end"], game_id) != receipt["game_sha_end"]: mismatch.append("game_files_end")
    if receipt["harness_files_end"] != manifest["harness_files"] or source_digest("harness", receipt["harness_files_end"]) != receipt["harness_sha_end"]: mismatch.append("harness_files_end")
    if not records or records[0]["manifest_sha256"] != manifest["manifest_sha256"]: mismatch.append("transcript_manifest_sha256")
    if receipt["transcript_head_chain_hash"] != records[-1]["chain_hash"]: mismatch.append("transcript_head_chain_hash")
    if receipt["transcript_record_count"] != len(records): mismatch.append("transcript_record_count")
    turns = count_turns(records)
    if receipt["turns"] != turns: mismatch.append("turns")
    if receipt["journal_sha256"] != journal_sha: mismatch.append("journal_sha256")
    if (receipt["journal_consistent"] is not True or receipt["journal_record_count"] != len(journal) or
            [item["turn_id"] for item in journal] != list(range(1, turns + 1))): mismatch.append("journal")
    return mismatch


def build_entry(run_dir, session_dir, turn_cap=None, judge_receipt_path=None):
    run_dir, session_dir = Path(run_dir), Path(session_dir)
    manifest = load_manifest(session_dir / "manifest.json")
    receipt = load_run_receipt(run_dir / "run_receipt.json")
    if isinstance(manifest, LegacyArtifact) or isinstance(receipt, LegacyArtifact):
        raise ValueError("legacy v1 evidence is readable but cannot be relabeled as a v2 ledger entry")
    records = load_transcript(session_dir / "transcript.jsonl")
    if getattr(records, "legacy", False): raise ValueError("legacy v1 transcript cannot enter a v2 ledger")
    journal_path = run_dir / "capsule" / "journal.jsonl"
    journal_data = journal_path.read_bytes() if journal_path.exists() else b""
    journal = _rows(journal_path)
    receipt_data = (run_dir / "run_receipt.json").read_bytes()
    mismatches = _verify_receipt_binding(receipt, manifest, records, _sha(journal_data), run_dir, journal)
    if turn_cap is not None and turn_cap != manifest["turn_cap"]: mismatches.append("turn_cap")
    # Recompute the finalized local artifacts. Hashes bind evidence; they do not defend against
    # a writer able to replace both artifact and receipt, which is outside this unit's threat model.
    for field, path in (("stdout_sha256", run_dir / "stdout.log"), ("stderr_sha256", run_dir / "stderr.log")):
        if not path.exists() or _sha(path.read_bytes()) != receipt[field]: mismatches.append(field)
    audit_path = run_dir / "stdout.log"
    audit_path = run_dir / "audit.log"
    if not audit_path.exists() or _sha(audit_path.read_bytes()) != receipt["audit_log_sha256"]: mismatches.append("audit_log_sha256")
    actual_head = records[-1]["chain_hash"] if records else None
    outcome = receipt["run_outcome"]
    game_id = manifest.get("game_id", "dnd_combat")
    detector_result = run_all(records, journal, game_id=game_id)
    detector_set_status = "IMPLEMENTED" if isinstance(detector_result, list) else detector_result["status"]
    instances = detector_result if isinstance(detector_result, list) else detector_result["instances"]
    detector_notes = list(getattr(detector_result, "notes", ()))
    verify_instance_quotes(records, instances)
    normalized = _normalize_detectors(records, instances, run_dir)
    judge_instances, judge_status = None, "NOT_REQUESTED"
    judge_hash, judge_version = None, None
    verifier_version = judge_model = judge_effort = None
    discarded = None
    if judge_receipt_path:
        try:
            judge = load_judge_receipt(judge_receipt_path)
            if isinstance(judge, LegacyArtifact): raise ValueError("legacy judge receipt")
            raw = Path(judge_receipt_path).read_bytes(); judge_hash = _sha(raw)
            judge_version, verifier_version = judge["judge_version"], judge["verifier_version"]
            judge_model, judge_effort = judge["judge_model"], judge["judge_effort"]
            bindings = (judge["run_id"] == manifest["run_id"] and
                judge["manifest_sha256"] == manifest["manifest_sha256"] and
                judge["transcript_head_chain_hash"] == actual_head and
                judge["journal_sha256"] == receipt["journal_sha256"] and
                judge["severity_taxonomy_version"] == manifest["severity_taxonomy_version"] and
                judge["bundle_sha256"] == _sha(build_judge_bundle(records, journal).encode("utf-8")) and
                judge["prompt_sha256"] == _sha(build_judge_prompt(build_judge_bundle(records, journal)).encode("utf-8")))
            if not bindings: judge_status = "INVALID"
            elif judge["judge_outcome"] != "COMPLETE": judge_status = "INCOMPLETE"
            else:
                judge_instances = []
                for item in judge["counted"]:
                    turns = item["turn_ids"]
                    if turns and (not item["quote"] or not any(item["quote"] in row["new_output"] for row in records if row["turn_id"] in turns)):
                        raise ValueError("judge quote is not in cited transcript")
                    expected_evidence = _evidence_sha(records, turns) if turns else None
                    if expected_evidence is not None and expected_evidence != item["evidence_sha256"]: raise ValueError("judge evidence digest mismatch")
                    judge_instances.append(item)
                discarded = judge["discarded_judge_claims"]
                judge_status = "COMPLETE"
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            judge_status = "INVALID"; judge_instances = None
    elif manifest["measurement_policy"] == "detector_and_judge":
        judge_status = "INCOMPLETE"
    eligibility = {"receipt_outcome": outcome}
    if mismatches: eligibility.update(comparison_eligible=False, reason_code="RECEIPT_MISMATCH:" + mismatches[0])
    elif outcome != "COMPLETE": eligibility.update(comparison_eligible=False, reason_code="RUN_OUTCOME_" + outcome)
    elif not count_turns(records): eligibility.update(comparison_eligible=False, reason_code="ZERO_ACTION_TURNS")
    elif manifest["measurement_policy"] == "detector_and_judge" and judge_status != "COMPLETE":
        eligibility.update(comparison_eligible=False, reason_code="JUDGE_" + judge_status)
    touched, encounters = set(), set()
    object_names = {obj["name"] for obj in manifest["content_catalog"]["objects"]}
    for row in records:
        snap = row["snapshot"]; rooms = snap.get("rooms", {})
        for room in rooms.values():
            for obj in room.get("objects", []):
                if isinstance(obj, dict) and obj.get("name") and obj.get("taken"): touched.add(obj["name"])
        calls = " ".join(row.get("input_calls", [])).casefold()
        for item in manifest["content_catalog"]["objects"]:
            if item["room_id"] == snap.get("room_id") and item["name"].casefold() in calls: touched.add(item["name"])
        if any(c.casefold().strip() in {"attack", "a", "use", "u", "potion"} for c in row["input_calls"]): encounters.add(snap.get("room_id"))
    for j in journal:
        intent = " ".join((j["wanted"], j["unsupported_intent"] or "")).casefold()
        touched.update(name for name in object_names if name.casefold() in intent)
    facts = session_facts(records)
    facts["objects_touched"] = len(touched); facts["encounters_faced"] = len(encounters)
    return make_entry(run_id=manifest["run_id"], session_id=manifest["session_id"],
        manifest_sha256=manifest["manifest_sha256"], run_receipt_sha256=_sha(receipt_data),
        journal_sha256=receipt["journal_sha256"], game_revision=manifest["game_revision"],
        harness_revision=manifest["harness_revision"], game_sha=manifest["game_sha"], harness_sha=manifest["harness_sha"],
        detector_version=DETECTOR_VERSION, persona_id=manifest["persona_id"],
        persona_prompt_sha256=manifest["persona_prompt_sha256"], seed=manifest["seed"],
        is_holdout=manifest["is_holdout"], holdout_prompt_sha256=manifest["holdout_prompt_sha256"],
        narrator_policy=manifest["narrator_policy"], turn_policy=manifest["turn_policy"],
        turn_cap=manifest["turn_cap"], measurement_policy=manifest["measurement_policy"],
        severity_taxonomy_version=manifest["severity_taxonomy_version"],
        golem_model=receipt["model"], golem_effort=receipt["effort"],
        judge_version=judge_version, verifier_version=verifier_version,
        judge_model=judge_model, judge_effort=judge_effort, judge_receipt_sha256=judge_hash,
        judge_status=judge_status, transcript_head_chain_hash=actual_head, run_outcome=outcome,
        termination=receipt["termination"], turns=count_turns(records), transcript_record_count=len(records),
        verified_instances=normalized + (judge_instances or []),
        discarded_judge_claims=discarded, curiosity=curiosity_events(records), coverage=facts,
        content_catalog=manifest["content_catalog"], eligibility_flags=eligibility,
        expected_content_change=None, game_id=game_id, schema_minor=manifest.get("schema_minor", 0),
        detector_set_status=detector_set_status, detector_notes=detector_notes)


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--run-dir", required=True); add.add_argument("--session-dir", required=True)
    add.add_argument("--ledger", required=True); add.add_argument("--judge-receipt")
    args = parser.parse_args(argv)
    if args.command == "add":
        entry = build_entry(args.run_dir, args.session_dir, judge_receipt_path=args.judge_receipt)
        stored = append_entry(args.ledger, entry); print(stored["entry_hash"])
    return 0


if __name__ == "__main__": raise SystemExit(main())
