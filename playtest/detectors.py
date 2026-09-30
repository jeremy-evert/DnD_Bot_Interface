"""Finite, deterministic measurements over verified playtest evidence."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
import re
from .schema import count_turns, SEVERITY_TAXONOMY
from .harness import snapshot as replay_snapshot

DETECTOR_VERSION = "1"


def _instance(mode, turns, quote, rationale, severity):
    severity = SEVERITY_TAXONOMY[mode]
    return {"mode": mode, "turn_ids": list(turns), "quote": quote,
            "rationale": rationale, "detector_version": DETECTOR_VERSION,
            "severity": severity}


def verify_instance_quotes(records, instances):
    by_id = {r["turn_id"]: r for r in records}
    for item in instances:
        if item["turn_ids"]:
            if not item["quote"] or not any(
                turn in by_id and item["quote"] in by_id[turn]["new_output"]
                for turn in item["turn_ids"]
            ):
                raise ValueError("detector quote is not present in a cited turn")
        elif item["quote"] and item["mode"] != "CONVENTION_CLASH":
            raise ValueError("static-only detector quote must be empty")
    return True


def _add(out, mode, record, quote, rationale, severity):
    if quote:
        out.append(_instance(mode, [record["turn_id"]], quote, rationale, severity))


class DetectorResults(list):
    """List-compatible detector instances plus non-counted diagnostic notes."""
    def __init__(self):
        super().__init__()
        self.notes = []


def _shortest(rooms, start, goal):
    if start == goal:
        return 0
    queue = deque([(start, 0)])
    seen = {start}
    while queue:
        room, distance = queue.popleft()
        for dest in rooms.get(room, {}).get("exits", {}).values():
            if dest == goal:
                return distance + 1
            if dest not in seen:
                seen.add(dest); queue.append((dest, distance + 1))
    return None


CONTRADICTION_RULES = [
    {"terms": ("sealed vault",), "exit_target": "sanctum", "description": "sealed"},
    {"terms": ("hidden door",), "exit_target": "sanctum", "description": "hidden"},
]

# Closed, data-driven evidence cues. Positive examples: "killed by the captain",
# "because you ignored the warning", "try again", and "carry the map onward".
# These are phrases, not a length or prose-quality heuristic.
DEATH_EVIDENCE_RULES = {
    "cause": (
        r"\bkilled by\b", r"\bstruck by\b", r"\bfell to\b", r"\bslain by\b",
        r"\b(?:because|after|when) you\b", r"\b(?:trap|poison|wound) caused\b",
    ),
    "retry": (r"\bretry\b", r"\btry again\b", r"\bnext time\b",
              r"\bstart over\b", r"\breturn to\b"),
    "carry_over": (
        r"\bcarry (?:the|your|this)\b", r"\b(?:map|clue|memory|lesson) (?:remains|stays|goes|travels)\b",
        r"\bremember\b", r"\bkeep .{0,30} for next time\b",
    ),
}
# Unknown prose is inconclusive. These explicit empty-terminal examples include
# the long empty wording that exposed the former length heuristic.
DEATH_EMPTY_TERMS = (
    "you have fallen", "you die", "the adventure ends here", "the story ends",
    "silence follows", "darkness fills the hall", "your journey stops here",
    "the last light goes out", "your story ends",
)
ACTIONABLE_INFORMATION_TERMS = (
    "reveals", "you discover", "you learn", "you notice", "you find out",
    "can be opened", "can open", "the way is", "the clue", "the warning",
    "points toward", "marks a", "shows you", "remembered what",
)


DETECTORS_NOT_IMPLEMENTED_FOR_GAME = "DETECTORS_NOT_IMPLEMENTED_FOR_GAME"


def run_all(records, journal=None, content=None, game_id="dnd_combat", receipt=None):
    if game_id == "delve":
        from .detectors_delve import run_all_delve
        return run_all_delve(records, journal=journal, content=content, receipt=receipt)
    if game_id != "dnd_combat":
        return {"status": "NOT_IMPLEMENTED", "marker": DETECTORS_NOT_IMPLEMENTED_FOR_GAME,
                "instances": []}
    out = DetectorResults()
    journal_rows = journal or []
    if isinstance(journal_rows, dict):
        journal_rows = list(journal_rows.values())
    journals = {j.get("turn_id"): j for j in journal_rows}
    for i, r in enumerate(records):
        text = r["new_output"]
        for phrase in ("Choose move, look, status, take, use, or talk.",
                       "Choose attack, use, or status."):
            if phrase in text:
                _add(out, "UNRECOGNIZED_COMMAND", r, phrase,
                     "Known game response to an invalid exploration or combat command.", 2)
                break
        j = journals.get(r["turn_id"], {})
        if j.get("unsupported_intent") and re.search(r"unrecognized|choose |cannot|no one|unsupported", text, re.I):
            _add(out, "UNSUPPORTED_INTENT", r, next((p for p in ("Choose move, look, status, take, use, or talk.", "Choose attack, use, or status.", "There is no one here to talk to.", "The stone compass cannot be taken.") if p in text), ""),
                 "Journal marks unsupported intent and cited output refuses it.", 3)
        if i and r["snapshot"].get("vault_opened") != records[i-1]["snapshot"].get("vault_opened"):
            rooms = r["snapshot"].get("rooms", {})
            dist_before = _shortest(rooms, r["snapshot"].get("room_id"), "sanctum")
            old_rooms = records[i-1]["snapshot"].get("rooms", {})
            dist_after = _shortest(old_rooms, records[i-1]["snapshot"].get("room_id"), "sanctum")
            # Change is measured at the player's current room at the transition.
            start = records[i-1]["snapshot"].get("room_id")
            old_distance = _shortest(old_rooms, start, "sanctum")
            new_distance = _shortest(rooms, start, "sanctum")
            if old_distance is not None and new_distance is not None and old_distance - new_distance < 2:
                _add(out, "HOLLOW_CONSEQUENCE", r, text.strip(),
                     "vault_opened changes the graph but saves fewer than two moves to sanctum.", 4)
        rooms = r["snapshot"].get("rooms", {})
        room_id = r["snapshot"].get("room_id")
        room = rooms.get(room_id, {})
        room_name = room.get("name", "")
        for rule in CONTRADICTION_RULES:
            if rule["exit_target"] in room.get("exits", {}).values() and all(t in (room_name + " " + text).lower() for t in rule["terms"]):
                quote = next((line for line in text.splitlines() if all(t in line.lower() for t in rule["terms"])), "")
                _add(out, "WORLD_STATE_CONTRADICTION", r, quote,
                     "Room text describes the vault as sealed/hidden while an open exit reaches sanctum.", 5)
                break
    if content and content.get("inert_takeables"):
        for name in content["inert_takeables"]:
            out.append(_instance("INERT_TAKEABLE", [], "", f"Takeable object has no reader rule: {name}.", 2))
    # No-consequence action frames and repeated normalized refusals.
    for i, r in enumerate(records):
        calls = [c.lower().strip() for c in r.get("input_calls", [])]
        if calls and calls[0] not in {"look", "l", "status", "s"}:
            refused = bool(re.search(r"Choose (?:move|attack)|unrecognized|cannot|no one here|no exit|no passage", r["new_output"], re.I))
            prev = records[i-1]["snapshot"].get("canonical_state_hash") if i else None
            now = r["snapshot"].get("canonical_state_hash")
            resolution = (" rolls " in r["new_output"] or " attacks! Initiative" in r["new_output"]
                          or re.search(r"(?:'s|’s) turn\.\.\.", r["new_output"]))
            informative = any(term in r["new_output"].lower()
                              for term in ACTIONABLE_INFORMATION_TERMS)
            if not refused and not resolution and not informative and prev and prev == now:
                _add(out, "NO_CONSEQUENCE_STALL", r, r["new_output"].strip(), "Apparently accepted non-query action left canonical state unchanged.", 4)
    grouped = defaultdict(list)
    state_epoch = 0
    previous_hash = object()
    for r in records:
        current_hash = r.get("snapshot", {}).get("canonical_state_hash")
        if not isinstance(current_hash, str) or not current_hash:
            # Unknown state breaks the evidence chain; it cannot prove a stall-free interval.
            state_epoch += 1
            previous_hash = object()
            continue
        if current_hash != previous_hash:
            state_epoch += 1
            previous_hash = current_hash
        lines = []
        for line in r["new_output"].splitlines():
            if (not line.strip() or "Your turn." in line or " HP, AC " in line
                    or " rolls " in line or "attacks! Initiative" in line
                    or line.endswith("'s turn...")):
                continue
            if line.strip().lower() in {call.strip().lower() for call in r.get("input_calls", [])}:
                continue
            lines.append(line.strip())
        response = " ".join(lines).lower()
        if response:
            grouped[(state_epoch, response)].append(r)
    for (state_epoch, response), rows in grouped.items():
        if len(rows) >= 3 and len({r["frame_id"] for r in rows}) >= 3:
            out.append(_instance("REPEATED_RESPONSE", [r["turn_id"] for r in rows], rows[0]["new_output"].strip(), "Same normalized response repeats across three frames without a material state change.", 3))
    decisions = [r for r in records if any(c.lower().strip() in {"attack", "a", "use", "u", "potion"} for c in r.get("input_calls", [])) and "Your turn." in r["new_output"]]
    attacks = sum(any(c.lower().strip() in {"attack", "a"} for c in r["input_calls"]) for r in decisions)
    if len(decisions) >= 5 and attacks / len(decisions) >= .9:
        r = decisions[-1]; _add(out, "DOMINANT_ACTION", r, "Your turn.", "At least five hero combat decisions; attack share is at least 90%.", 3)
    if len(decisions) >= 5 and attacks / len(decisions) >= .8:
        r = decisions[-1]; _add(out, "DOMINANT_ACTION_SOFT", r, "Your turn.", "At least five hero combat decisions; attack share is at least 80%.", 1)
    if records and (records[-1]["termination"] == "dead"
                    or records[-1].get("snapshot", {}).get("game_state") == "dead"):
        r = records[-1]
        lines = r["new_output"].splitlines()
        combat_lines = [i for i, line in enumerate(lines) if " rolls " in line]
        terminal = "\n".join(lines[combat_lines[-1] + 1:] if combat_lines else lines).strip()
        lowered = terminal.lower()
        has_evidence = any(re.search(pattern, lowered, re.I)
                           for patterns in DEATH_EVIDENCE_RULES.values() for pattern in patterns)
        is_known_empty = any(term in lowered for term in DEATH_EMPTY_TERMS)
        if terminal and is_known_empty and not has_evidence:
            _add(out, "FAIL_WITH_NOTHING", r, terminal, "Death message gives no cause, retry path, or carry-over.", 3)
        elif terminal and not has_evidence and not is_known_empty:
            out.notes.append({"kind": "INCONCLUSIVE", "mode": "FAIL_WITH_NOTHING",
                              "turn_ids": [r["turn_id"]], "quote": terminal,
                              "rationale": "Death wording matches neither cause/retry/carry-over evidence nor the explicit empty-terminal examples.",
                              "detector_version": DETECTOR_VERSION})
    out.extend(probe_conventions())
    return out


def probe_conventions():
    from .harness import replay
    result = replay(1, ["Probe", "fighter", "north"])
    quote = "Choose move, look, status, take, use, or talk."
    instances = []
    if quote in result.output:
        item = _instance("CONVENTION_CLASH", [], quote, "probe: bare north is unrecognized at the top prompt.", 2)
        item["probe_artifact"] = {"probe_version": 1, "seed": 1,
            "input_calls": ["Probe", "fighter", "north"], "output": result.output,
            "snapshot": replay_snapshot(result.witness)}
        instances.append(item)
    result = replay(1, ["Probe", "fighter", "s"])
    if "Probe the Fighter:" in result.output:
        item = _instance("CONVENTION_CLASH", [], "Probe the Fighter:", "probe: s resolves to status rather than south.", 2)
        item["probe_artifact"] = {"probe_version": 1, "seed": 1,
            "input_calls": ["Probe", "fighter", "s"], "output": result.output,
            "snapshot": replay_snapshot(result.witness)}
        instances.append(item)
    return instances


def curiosity_events(records):
    rooms = [r["snapshot"].get("room_id") for r in records]
    entered = set()
    previous = None
    for room in rooms:
        if room != previous and room is not None: entered.add(room)
        previous = room
    earned = 0
    for i, r in enumerate(records):
        if not i or not r.get("input_calls"):
            continue
        before, after = records[i-1]["snapshot"], r["snapshot"]
        old_inventory = before.get("inventory", [])
        if any(item not in old_inventory for item in after.get("inventory", [])):
            earned += 1; continue
        if any(item not in before.get("known_clues", []) for item in after.get("known_clues", [])):
            earned += 1; continue
        if any(item not in before.get("flags", []) for item in after.get("flags", [])):
            earned += 1; continue
        old_rooms, new_rooms = before.get("rooms", {}), after.get("rooms", {})
        if any(new_rooms.get(key, {}).get("exits") != room.get("exits") for key, room in old_rooms.items()):
            earned += 1; continue
        if any(room.get("enemy", {}).get("alive") and not new_rooms.get(key, {}).get("enemy", {}).get("alive") for key, room in old_rooms.items() if room.get("enemy")):
            earned += 1
    callback = sum(bool(re.search(r"remember|recognizes|again|remains", r["new_output"], re.I)) for r in records)
    clues = {clue for r in records for clue in r["snapshot"].get("known_clues", [])}
    flags = {flag for r in records for flag in r["snapshot"].get("flags", [])}
    return {"DISCOVERY": len(entered), "EARNED_CONSEQUENCE": earned, "CALLBACK": callback,
            "rooms_visited": len(entered), "distinct_clues": len(clues),
            "distinct_flags": len(flags), "turns": count_turns(records)}


def session_facts(records):
    rooms = {r["snapshot"].get("room_id") for r in records if r["snapshot"].get("room_id")}
    combat = sum(any(c.lower().strip() in {"attack", "a", "use", "u", "potion"} for c in r.get("input_calls", [])) and "Your turn." in r["new_output"] for r in records)
    attacks = sum(any(c.lower().strip() in {"attack", "a"} for c in r.get("input_calls", []))
                  for r in records if any(c.lower().strip() in {"attack", "a", "use", "u", "potion"} for c in r.get("input_calls", [])) and "Your turn." in r["new_output"])
    return {"turns": count_turns(records), "termination": records[-1]["termination"] if records else None,
            "rooms_visited": len(rooms), "hero_combat_decisions": combat,
            "attack_share": attacks / combat if combat else 0.0}
