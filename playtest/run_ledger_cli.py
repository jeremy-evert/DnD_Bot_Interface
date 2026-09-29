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


def build_entry(run_dir, session_dir):
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
    return make_entry(run_id=manifest["session_id"], game_sha=receipt.get("game_sha", manifest["game_sha"]),
                      harness_sha=receipt.get("harness_sha", manifest["harness_sha"]), detector_version=DETECTOR_VERSION,
                      persona_id=manifest["persona_id"], seed=manifest["seed"], is_holdout=False,
                      narrator_policy=manifest["narrator_policy"], turn_cap=receipt.get("turn_cap", receipt.get("turns_taken", 35)),
                      golem_model=receipt.get("model"), golem_effort=receipt.get("effort"),
                      transcript_head_chain_hash=receipt.get("transcript_head_chain_hash") or (records[-1]["chain_hash"] if records else None),
                      run_outcome=outcome, termination=receipt.get("termination") or (records[-1]["termination"] if records else None),
                      turns=receipt.get("turns_taken", len(records)), instances=instances, curiosity=curiosity_events(records),
                      coverage={**session_facts(records), "objects_touched": len(touched), "encounters_faced": len(encounters)},
                      unsupported_intents=[j["unsupported_intent"] for j in journal if j.get("unsupported_intent")],
                      eligibility_flags={"receipt_outcome": outcome})


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--run-dir", required=True); add.add_argument("--session-dir", required=True); add.add_argument("--ledger", required=True)
    args = parser.parse_args(argv)
    if args.command == "add":
        entry = build_entry(args.run_dir, args.session_dir)
        stored = append_entry(args.ledger, entry)
        print(stored["entry_hash"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
