"""Create a ledger entry from a receipted run and verified controller artifacts."""
import argparse
import json
from pathlib import Path

from .detectors import DETECTOR_VERSION, curiosity_events, run_all, session_facts, verify_instance_quotes
from .ledger import append_entry, make_entry
from .transcript import load_transcript


def _rows(path):
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _content_inventory(records):
    """Count map content in the initial verified snapshot, not visited content."""
    snapshot = records[0].get("snapshot", {}) if records else {}
    rooms = snapshot.get("rooms", {})
    objects = [item for room in rooms.values() for item in room.get("objects", []) if isinstance(item, dict)]
    enemies = sum(1 for room in rooms.values() if room.get("enemy"))
    exits = sum(len(room.get("exits", {})) for room in rooms.values())
    return {"total_rooms": len(rooms), "total_objects": len(objects),
            "total_takeables": sum(bool(item.get("takeable")) for item in objects),
            "total_enemies": enemies, "total_exits": exits}


def build_entry(run_dir, session_dir, turn_cap=None):
    run_dir, session_dir = Path(run_dir), Path(session_dir)
    receipt = json.loads((run_dir / "run_receipt.json").read_text(encoding="utf-8"))
    manifest = json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
    records = load_transcript(session_dir / "transcript.jsonl")
    journal = _rows(run_dir / "capsule" / "journal.jsonl")
    outcome = receipt.get("outcome", "ERROR")
    if outcome not in {"COMPLETE", "INCOMPLETE_DISPATCH", "BLINDNESS_VIOLATED", "AUDIT_UNVERIFIABLE", "ERROR"}:
        outcome = "ERROR"
    instances = run_all(records, journal)
    verify_instance_quotes(records, instances)
    touched, encounters = set(), set()
    object_names = set()
    for row in records:
        rooms = row.get("snapshot", {}).get("rooms", {})
        for obj in rooms.values():
            for item in obj.get("objects", []):
                if isinstance(item, dict) and item.get("name"):
                    object_names.add(item["name"])
                    if item.get("taken"):
                        touched.add(item["name"])
        calls = " ".join(row.get("input_calls", [])).casefold()
        current_room = rooms.get(row.get("snapshot", {}).get("room_id"), {})
        for item in current_room.get("objects", []):
            if isinstance(item, dict) and item.get("name") and item["name"].casefold() in calls:
                touched.add(item["name"])
        if any(c.lower().strip() in {"attack", "a", "use", "u", "potion"} for c in row.get("input_calls", [])) and "Your turn." in row.get("new_output", ""):
            encounters.add(row.get("snapshot", {}).get("room_id"))
    for journal_row in journal:
        intent = " ".join((journal_row.get("wanted", ""), journal_row.get("unsupported_intent") or "")).casefold()
        touched.update(name for name in object_names if name.casefold() in intent)
    mismatches = []
    for field in ("game_sha", "harness_sha"):
        if field in receipt and field in manifest and receipt[field] != manifest[field]: mismatches.append(field)
    actual_head = records[-1]["chain_hash"] if records else None
    actual_turns = len(records)
    if receipt.get("transcript_head_chain_hash") is not None and receipt["transcript_head_chain_hash"] != actual_head:
        mismatches.append("transcript_head_chain_hash")
    if receipt.get("turns_taken") is not None and receipt["turns_taken"] != actual_turns: mismatches.append("turns")
    selected_cap = turn_cap if turn_cap is not None else receipt.get("turn_cap")
    # Older receipts without the explicit post-exit finalization claim remain
    # auditable but cannot be used for comparison.
    receipt_unfinalized = receipt.get("receipt_finalized_after_child_exit") is not True
    eligibility = {"receipt_outcome": outcome}
    if mismatches:
        eligibility.update(comparison_eligible=False, reason_code="RECEIPT_MISMATCH:" + mismatches[0])
    elif receipt_unfinalized:
        eligibility.update(comparison_eligible=False, reason_code="RECEIPT_NOT_FINALIZED")
    elif selected_cap is None:
        eligibility.update(comparison_eligible=False, reason_code="TURN_CAP_UNKNOWN")
    elif outcome != "COMPLETE":
        eligibility.update(comparison_eligible=False, reason_code="RUN_OUTCOME_" + outcome)
    return make_entry(run_id=manifest["session_id"], game_sha=receipt.get("game_sha", manifest["game_sha"]),
                      harness_sha=receipt.get("harness_sha", manifest["harness_sha"]), detector_version=DETECTOR_VERSION,
                      persona_id=manifest["persona_id"], seed=manifest["seed"], is_holdout=receipt.get("is_holdout", False),
                      holdout_prompt_sha256=receipt.get("holdout_prompt_sha256"),
                      narrator_policy=manifest["narrator_policy"], turn_cap=selected_cap,
                      golem_model=receipt.get("model"), golem_effort=receipt.get("effort"),
                      transcript_head_chain_hash=actual_head,
                      run_outcome=outcome, termination=receipt.get("termination") or (records[-1]["termination"] if records else None),
                      turns=actual_turns, instances=instances, curiosity=curiosity_events(records),
                      coverage={**session_facts(records), "objects_touched": len(touched), "encounters_faced": len(encounters)},
                      content_inventory=_content_inventory(records),
                      judge_instances=receipt.get("judge_instances", ()),
                      discarded_judge_claims=receipt.get("discarded_judge_claims", 0),
                      unsupported_intents=[j["unsupported_intent"] for j in journal if j.get("unsupported_intent")],
                      eligibility_flags=eligibility)


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--run-dir", required=True); add.add_argument("--session-dir", required=True); add.add_argument("--ledger", required=True)
    add.add_argument("--turn-cap", type=int)
    args = parser.parse_args(argv)
    if args.command == "add":
        entry = build_entry(args.run_dir, args.session_dir, turn_cap=args.turn_cap)
        stored = append_entry(args.ledger, entry)
        print(stored["entry_hash"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
