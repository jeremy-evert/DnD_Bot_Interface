"""Delve detector fixtures. REAL rows are copied controller evidence; twins are patched replays."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
import re

from .harness import replay, snapshot

ROOT = Path(__file__).resolve().parent / "fixtures" / "real_delve"
PILOT1 = Path(__file__).resolve().parent / "fixtures" / "real" / "pilot1_explorer"

REAL_HARNESS_PROVENANCE = (
    ("12 controller pilots", "fixtures/real_delve/{delve_*,delve2_*,delve3_*}", "REAL_HARNESS"),
    ("D&D command tax probe", "fixtures/real/{pilot1..pilot4}", "REAL_HARNESS"),
    ("no_progress stop", "run_receipt.json stop_reason", "REAL_CONTROLLER_RECEIPT"),
)
SYNTHETIC_TWINS = (
    ("MISSING_TELEGRAPH", "patched render_status omits enemy intent in real replay"),
    ("FAIL_WITH_NOTHING", "patched low-HP state and death renderer in real replay"),
    ("REPEATED_RESPONSE", "stable-state transcript twin cloned from a real help frame"),
    ("DOMINANT_ACTION", "attack-heavy transcript twin cloned from real combat frames"),
    ("LATENCY_BREAK", "injected 100 ms/action measurement threshold twin"),
)

def load_rows(path):
    # The supplied pilot bundle has per-row hash chains, but no external .head file.
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]

def real_sessions():
    result = {}
    for folder in sorted(ROOT.iterdir()):
        if folder.is_dir() and (folder / "transcript.jsonl").exists():
            result[folder.name] = {
                "records": load_rows(folder / "transcript.jsonl"),
                "journal": load_rows(folder / "journal.jsonl"),
                "receipt": json.loads((folder / "run_receipt.json").read_text(encoding="utf-8")),
                "manifest": json.loads((folder / "manifest.json").read_text(encoding="utf-8")),
            }
    return result

def input_tax_probe():
    """REAL_HARNESS twin: pilot1_explorer's move frames require command + direction."""
    return load_rows(PILOT1 / "transcript.jsonl")

def real_delve_run(inputs, seed=731):
    """Run the actual entry point and retain a transcript-like final action witness."""
    result = replay(seed, ["f", *inputs], game_id="delve")
    row = {"turn_id": 1, "frame_id": 1, "frame_kind": "action", "input_calls": list(inputs),
           "new_output": result.output, "snapshot": snapshot(result.witness, "delve") if result.witness else {},
           "termination": "playing"}
    return result, [row]

def missing_telegraph_twin(seed=3):
    """REAL_HARNESS twin with only the status renderer's enemy intent removed."""
    import delve.__main__ as main
    from .harness import replay, snapshot
    real_status = main.render_status
    def omit_intent(*args, **kwargs):
        value = real_status(*args, **kwargs)
        return "\n".join(line for line in value.splitlines()
                         if not re.match(r"^(?:Goblin|Hobgoblin Captain) \d+/\d+ HP", line))
    with patch.object(main, "render_status", side_effect=omit_intent):
        result = replay(seed, ["f", "b", "b"], game_id="delve")
    initial = replay(seed, ["f"], game_id="delve")
    before = {"player": {"hp": 24}, "room_id": "mossy_entry",
              "enemies": snapshot(initial.witness, "delve")["enemies"],
              "canonical_state_hash": "initial"}
    after = snapshot(result.witness, "delve")
    rows = [
        {"turn_id": 0, "frame_id": 0, "frame_kind": "setup", "input_calls": ["f"],
         "new_output": result.output, "snapshot": before, "termination": "playing"},
        {"turn_id": 1, "frame_id": 1, "frame_kind": "action", "input_calls": ["b"],
         "new_output": result.output, "snapshot": after, "termination": "playing"},
    ]
    return result, rows

def fail_with_nothing_twin(seed=731):
    """REAL_HARNESS twin with low HP and an intentionally unhelpful death renderer."""
    import delve.__main__ as main
    import delve.state as state_module
    from .harness import replay, snapshot
    real_new = state_module.DelveState.new
    def one_hp(*args, **kwargs):
        state = real_new(*args, **kwargs); state.player["hp"] = 1; return state
    with patch.object(state_module.DelveState, "new", side_effect=one_hp), \
         patch.object(main, "render_death", return_value="YOU DIED — The dark takes you."):
        result = replay(seed, ["f", "b", "b", "q"], game_id="delve")
    snap = snapshot(result.witness, "delve")
    row = {"turn_id": 1, "frame_id": 1, "frame_kind": "action", "input_calls": ["b"],
           "new_output": result.output, "snapshot": snap,
           "termination": "dead" if snap.get("terminal") == "dead" else "playing"}
    return result, [row]

def action_row(turn, command, output, state, *, frame_kind="action"):
    return {"turn_id": turn, "frame_id": turn, "frame_kind": frame_kind,
            "input_calls": list(command), "new_output": output, "snapshot": state,
            "termination": "playing"}

def patched_telegraph_twin(real_rows):
    """SYNTHETIC twin: real HP-loss frame, with the preceding status intent line removed."""
    rows = [dict(r) for r in real_rows]
    for r in rows:
        r["snapshot"] = dict(r.get("snapshot", {}))
    for i in range(1, len(rows)):
        before = rows[i-1].get("snapshot", {}).get("player", {}).get("hp", 0)
        after = rows[i].get("snapshot", {}).get("player", {}).get("hp", 0)
        if after < before:
            rows[i-1]["new_output"] = ""
            return rows
    return rows
