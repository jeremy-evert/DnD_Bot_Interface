"""Finite, transcript based measurements for Fast Delve M1."""
from __future__ import annotations

from collections import defaultdict
import json
import re
import time
from unittest.mock import patch
from pathlib import Path

from .schema import SEVERITY_TAXONOMY, count_turns

DETECTOR_VERSION_DELVE = "delve-1"


class DetectorResults(list):
    def __init__(self):
        super().__init__()
        self.notes = []
        self.probe_artifacts = []


def _instance(mode, turns, quote, rationale, *, artifact=None):
    return {"mode": mode, "turn_ids": list(turns), "quote": quote,
            "rationale": rationale, "detector_version": DETECTOR_VERSION_DELVE,
            "severity": SEVERITY_TAXONOMY[mode],
            **({"probe_artifact": artifact} if artifact is not None else {})}


def _add(out, mode, row, quote, rationale):
    if quote and quote in row.get("new_output", ""):
        out.append(_instance(mode, [row["turn_id"]], quote, rationale))


REFUSAL_KEYS = {
    # Parser-level refusals: the command or requested target was not understood.
    "parse.unknown_verb", "target.unknown", "target.ambiguous",
    # Valid commands refused because their target/object cannot be acted on now.
    "target.not_held", "move.no_exit", "move.blocked", "get.blocked",
    "get.not_takeable", "use.nothing", "retreat.help",
}

# Classification is intentionally exhaustive (checked against the current pack
# in tests). throw.fizzle is a consequence: the item is spent and the enemy's
# attack still resolves, so its message must not suppress consequence checks.
NOT_A_REFUSAL = {
    "look.held": "Flavor text for inspecting a held item; it does not reject a request.",
    "room.entry": "Scene description; it does not reject a player request.",
    "room.observatory": "Scene description; it does not reject a player request.",
    "room.chart_chamber": "Scene description; it does not reject a player request.",
    "room.gallery": "Scene description; it does not reject a player request.",
    "room.vault": "Scene description; it does not reject a player request.",
    "room.enter": "Movement consequence and room arrival narration.",
    "room.return": "Arrival narration after returning to a room.",
    "object.read": "Successful object inspection output.",
    "item.get": "Successful inventory change.",
    "intent.goblin.grab": "Enemy intent telegraph, not a player-action refusal.",
    "intent.goblin.strike": "Enemy intent telegraph, not a player-action refusal.",
    "intent.captain.guard": "Enemy intent telegraph, not a player-action refusal.",
    "intent.captain.smash": "Enemy intent telegraph, not a player-action refusal.",
    "attack.hit": "Combat resolution with a mechanical consequence.",
    "attack.miss": "Combat resolution with a mechanical consequence.",
    "shove.success": "Combat resolution with a mechanical consequence.",
    "shove.fail": "Combat resolution with an attempted action resolution.",
    "brace.success": "Combat resolution of the defensive action.",
    "throw.interrupt": "Combat resolution; the enemy's attack is interrupted.",
    "hazard.trigger": "Hazard consequence applied by the engine.",
    "clock.tick": "Persistent world clock consequence.",
    "clock.threshold": "Persistent world clock threshold consequence.",
    "clue.reveal": "Successful information discovery.",
    "fact.payoff": "Successful discovery payoff with actionable information.",
    "terminal.victory": "Terminal success state and victory narration.",
    "terminal.death": "Terminal failure state and cause narration.",
    "terminal.retry": "Retry guidance after a terminal outcome.",
    "clue.mira": "Successful clue discovery.",
    "clue.chart": "Successful clue discovery.",
    "clue.dome": "Successful clue discovery.",
    "inventory": "Successful query response listing inventory.",
    "help": "Successful query response listing commands.",
    "terminal.quit": "Terminal quit response.",
    "brace.wasted": "Action resolves as a defensive attempt without an intent to meet.",
    "throw.fizzle": "Consequence: the throw changes the encounter and the enemy attack proceeds.",
    "intent.cancelled": "Enemy intent state change caused by combat.",
    "enemy.hit": "Enemy combat resolution with a mechanical consequence.",
    "enemy.miss": "Enemy combat resolution with a mechanical consequence.",
    "retreat.blocked": "Combat retreat resolution, governed by the encounter state.",
    "terminal.closed": "Terminal response after the game closes.",
    "enemy.defeated": "Combat consequence that changes enemy state.",
    "throw.cup": "Successful item-specific throw narration and combat effect.",
    "throw.leaf": "Successful item-specific throw narration and combat effect.",
    "clock.threshold.patrol.2": "Persistent world clock threshold consequence.",
    "clock.threshold.patrol.4": "Persistent world clock threshold consequence.",
    "object.compass": "Successful object inspection output.",
    "item.use.bowl": "Successful item use narration or effect.",
    "item.use.ring": "Successful item use narration or effect.",
    "object.nameplate": "Successful object inspection output.",
    "object.ring": "Successful object inspection output.",
    "object.dome": "Successful object inspection output.",
    "object.bell": "Successful object inspection output.",
    "object.chart": "Successful object inspection output.",
    "object.cup": "Successful object inspection output.",
    "object.leaf": "Successful object inspection output.",
    "object.bowl": "Successful object inspection output.",
    "hazard.hint.unknown": "Informational hazard description; it does not refuse inspection.",
    "hazard.hint.known": "Informational hazard description; it does not refuse inspection.",
}


def _bank_entries():
    from delve.pack import load_engine_ready_pack
    pack = load_engine_ready_pack(Path(__file__).resolve().parents[1] / "delve" / "content" / "mossy_fast_slice.json")
    return {entry.key: entry for entry in pack.bank}, pack


def _template_pattern(template):
    """Escape authored text while treating each {{slot}} as a lazy wildcard."""
    chunks = re.split(r"({{[a-zA-Z0-9_]+}})", template)
    pattern = "".join(r".+?" if re.fullmatch(r"{{[a-zA-Z0-9_]+}}", chunk)
                      else re.escape(chunk) for chunk in chunks)
    # The line may have renderer-added text following a bank message. Refusal
    # recognition only trusts a bank phrase at the start of a response line.
    return re.compile("^" + pattern, re.I)


def refusal_templates(pack):
    """Compile all variants (and fallback-only text) for classified refusals."""
    if hasattr(pack, "bank"):
        entries = pack.bank
    elif "bank" in pack:
        bank = pack["bank"]
        entries = bank.get("entries", ()) if isinstance(bank, dict) else bank
    else:
        entries = pack.get("entries", ())
    result = []
    for entry in entries:
        key = entry.key if hasattr(entry, "key") else entry["key"]
        if key not in REFUSAL_KEYS:
            continue
        variants = entry.variants if hasattr(entry, "variants") else entry.get("variants", ())
        fallback = entry.fallback if hasattr(entry, "fallback") else entry.get("fallback", "")
        for template in dict.fromkeys((*variants, fallback)):
            if template:
                result.append(_template_pattern(template))
    return result


def _legacy_bank_for_game_sha(game_sha):
    """Resolve a recorded game build to the bank bytes named by its manifest."""
    from .fixtures_delve import content_sha_for_game_sha, legacy_bank_path
    content_sha = content_sha_for_game_sha(game_sha)
    path = legacy_bank_path(content_sha) if content_sha else None
    if path is None:
        return None
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _pack_for_records(records, current_pack):
    game_shas = {row.get("game_sha") for row in records if row.get("game_sha")}
    if not game_shas:
        return current_pack
    if len(game_shas) != 1:
        return None
    game_sha = next(iter(game_shas))
    # The running checkout itself is a known build and uses the loaded current
    # pack. This also covers fresh harness replays whose manifest is not archived.
    from .schema import source_manifest
    root = Path(__file__).resolve().parents[1]
    if source_manifest(root, "game", game_id="delve")["sha256"] == game_sha:
        return current_pack
    bank = _legacy_bank_for_game_sha(game_sha)
    if bank is None:
        return None
    return bank


def _is_refusal(text, patterns):
    return any(p.search(line.strip()) for p in patterns for line in text.splitlines())


MATERIAL_SNAPSHOT_FIELDS = frozenset({
    "player", "room_id", "inventory", "present_objects", "flags",
    "known_clues", "known_facts", "clocks", "enemies", "terminal",
})
# Snapshot bookkeeping/configuration has no direct game consequence: event/turn
# accounting, RNG accounting, narration memory, canonical digest, and run identity.
BOOKKEEPING_SNAPSHOT_FIELDS = frozenset({
    "turn", "event_log", "bank_memory", "rng_draws", "canonical_state_hash",
    "seed", "pack_id",
})


def material_state(snapshot):
    """Return the consequence-bearing snapshot projection used by stall detectors."""
    unknown = set(snapshot) - MATERIAL_SNAPSHOT_FIELDS - BOOKKEEPING_SNAPSHOT_FIELDS
    if unknown:
        raise ValueError(f"unclassified Delve snapshot fields: new={sorted(unknown)}")
    return {key: snapshot[key] for key in sorted(MATERIAL_SNAPSHOT_FIELDS) if key in snapshot}


def _material_hash(row):
    snapshot = row.get("snapshot", {})
    if not snapshot:
        return None
    # The shared test probe also passes D&D snapshots through this Delve module.
    if "pack_id" not in snapshot:
        return snapshot.get("canonical_state_hash")
    canonical = json.dumps(material_state(snapshot), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    import hashlib
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parsed_action(calls):
    """Return parser canonical action based on Delve's command alias table."""
    if not calls:
        return None
    from delve.commands import ALIAS_ACTIONS
    words = calls[0].strip().casefold().split()
    if not words:
        return None
    first = words[0]
    phrase = " ".join(words)
    if phrase in ALIAS_ACTIONS:
        first = phrase
    return ALIAS_ACTIONS.get(first)


def _query(calls):
    return _parsed_action(calls) in {"look", "inventory", "help", "quit"}


def _is_action(row):
    return row.get("frame_kind") == "action" or (
        "frame_kind" not in row and type(row.get("turn_id")) is int and row["turn_id"] > 0)


def _state_hash(row):
    return _material_hash(row)


def _status_enemy_lines(text):
    headers = list(re.finditer(r"^[A-Z][A-Z ]+ \[[^]]+\]  HP \d+/\d+", text, re.M))
    if not headers:
        return []
    tail = text[headers[-1].start():]
    return re.findall(r"^(Goblin|Hobgoblin Captain) \d+/\d+ HP \[[^]]+\] — .+$", tail, re.M)


def _response(row):
    calls = {c.strip().casefold() for c in row.get("input_calls", [])}
    lines = []
    for line in row.get("new_output", "").splitlines():
        value = line.strip()
        if (not value or value.casefold() in calls or value.startswith(">") or
                re.match(r"^[A-Z][A-Z ]+ \[[^]]+\]  HP ", value) or
                re.match(r"^(?:Goblin|Hobgoblin Captain) \d+/\d+ HP", value) or
                value.startswith(("Objects:", "Hazard:", "PATROL "))):
            continue
        lines.append(value)
    return " ".join(lines).casefold()


def _combat_decisions(records):
    verbs = {"a", "attack", "hit", "strike", "fight", "swing", "slash", "heavy",
             "b", "brace", "sh", "shove", "push", "t", "throw", "ret", "retreat", "u", "use"}
    result = []
    for row in records:
        calls = row.get("input_calls", [])
        if _is_action(row) and calls and calls[0].strip().casefold() in verbs:
            if _status_enemy_lines(row.get("new_output", "")) or re.search(r"Solid hit:|A miss\.|Nothing lands\.|Braced:", row.get("new_output", ""), re.I):
                result.append(row)
    return result


def run_all_delve(records, journal=None, content=None, receipt=None):
    """Run Delve transcript detectors and pack-backed static audits."""
    out = DetectorResults()
    journals = journal or []
    if isinstance(journals, dict):
        journals = list(journals.values())
    journals = {item.get("turn_id"): item for item in journals}
    _, loaded_pack = _bank_entries()
    transcript_pack = _pack_for_records(records, loaded_pack)
    refusals = refusal_templates(transcript_pack) if transcript_pack is not None else []
    if transcript_pack is None and records:
        out.notes.append({"kind": "INCONCLUSIVE", "mode": "UNRECOGNIZED_COMMAND",
                          "turn_ids": [], "quote": "",
                          "rationale": "refusal templates unavailable for this build",
                          "detector_version": DETECTOR_VERSION_DELVE})
    enemy_rooms = {enemy.id: enemy.room_id for enemy in loaded_pack.enemies}
    informative = re.compile(r"reveals|you discover|you learn|you notice|you find out|can be opened|the clue|the warning|points toward|shows you|remembered what", re.I)
    resolution = re.compile(r"solid hit:|\bhit\.|a miss\.|nothing lands\.|takes \d+ (?:damage|out of you)|\d+ damage|braced:|you make yourself a wall|you heft|the fight leaves|goes down", re.I)

    for i, row in enumerate(records):
        text = row.get("new_output", "")
        refusal_line = next((line.strip() for line in text.splitlines()
                             if any(p.match(line.strip()) for p in refusals)), "")
        if refusal_line:
            _add(out, "UNRECOGNIZED_COMMAND", row, refusal_line,
                 "The game refused an unknown verb, target, or unavailable action.")
            if journals.get(row.get("turn_id"), {}).get("unsupported_intent"):
                _add(out, "UNSUPPORTED_INTENT", row, refusal_line,
                     "Journal marks unsupported intent and the cited game output refuses it.")

        calls = row.get("input_calls", [])
        if i and _is_action(row) and calls and not _query(calls) and not refusal_line:
            before, after = _state_hash(records[i - 1]), _state_hash(row)
            response = _response(row)
            # A stall requires a repeated no-effect response, not one resolved
            # failure. This catches loops while preserving isolated attempts.
            prior = records[i - 1]
            prior_response = _response(prior)
            prior_calls = prior.get("input_calls", [])
            if (before and before == after and response and response == prior_response and
                    _is_action(prior) and prior_calls and not _query(prior_calls) and
                    not _is_refusal(prior.get("new_output", ""), refusals) and
                    not informative.search(text) and not resolution.search(text)):
                quote = next((line.strip() for line in text.splitlines()
                              if line.strip() and not line.strip().startswith(("MOSSY ", "HOLLOW ", "COLLAPSED ", "VAULT ", "Goblin ", "Hobgoblin Captain ", ">"))), "")
                _add(out, "NO_CONSEQUENCE_STALL", row, quote,
                     "Accepted non-query action repeated the prior response without changing material state or revealing information.")

        # The previous transcript frame is the only permitted source for telegraph evidence.
        if i and _is_action(row):
            before = records[i - 1].get("snapshot", {})
            after = row.get("snapshot", {})
            if after.get("player", {}).get("hp", 0) < before.get("player", {}).get("hp", 0):
                prior = records[i - 1].get("new_output", "")
                prior_enemies = before.get("enemies", {})
                living = any(enemy.get("hp", 0) > 0 and enemy.get("alive", True)
                             and enemy_rooms.get(enemy_id) == before.get("room_id")
                             for enemy_id, enemy in prior_enemies.items())
                if living and not _status_enemy_lines(prior):
                    quote = next((line.strip() for line in text.splitlines() if line.strip()), "")
                    _add(out, "MISSING_TELEGRAPH", row, quote,
                         "Hero HP fell while a living enemy had no intent line in the preceding output frame.")

        if _is_action(row) and len(calls) > 1:
            quote = next((line.strip() for line in text.splitlines() if line.strip()), "")
            _add(out, "INPUT_TAX", row, quote, "One action frame consumed multiple terminal input calls.")

    # Repeated answers require known, unchanged material state and separate frames.
    groups = defaultdict(list)
    epoch, previous = 0, object()
    for row in records:
        state = _state_hash(row)
        if not state:
            epoch += 1; previous = object(); continue
        if state != previous:
            epoch += 1; previous = state
        response = _response(row)
        if response and not _is_refusal(response, refusals):
            groups[(epoch, response)].append(row)
    for rows in groups.values():
        if len(rows) >= 3 and len({r.get("frame_id") for r in rows}) >= 3:
            quote = next((line.strip() for line in rows[0]["new_output"].splitlines()
                          if line.strip() and not line.strip().startswith(("MOSSY ", "HOLLOW ", "COLLAPSED ", "VAULT ", "Goblin ", "Hobgoblin Captain ", ">"))), "")
            if quote:
                out.append(_instance("REPEATED_RESPONSE", [r["turn_id"] for r in rows], quote,
                    "Same response repeats in three distinct frames without an intervening material state change."))

    decisions = _combat_decisions(records)
    attacks = sum(r["input_calls"][0].strip().casefold() in {"a", "attack", "hit", "strike", "fight", "swing", "slash", "heavy"} for r in decisions)
    attack_share = attacks / len(decisions) if decisions else 0.0
    if len(decisions) >= 5:
        row = decisions[-1]
        quote = next((line.strip() for line in row["new_output"].splitlines() if line.strip()), "")
        if attack_share >= .9:
            _add(out, "DOMINANT_ACTION", row, quote, f"Attack share is {attack_share:.3f} over {len(decisions)} combat decisions (>= 0.90).")
        if attack_share >= .8:
            _add(out, "DOMINANT_ACTION_SOFT", row, quote, f"Attack share is {attack_share:.3f} over {len(decisions)} combat decisions (>= 0.80).")

    if records and (records[-1].get("termination") == "dead" or records[-1].get("snapshot", {}).get("terminal") == "dead"):
        row = records[-1]
        text = row.get("new_output", "")
        death = text[text.rfind("YOU DIED"):] if "YOU DIED" in text else text
        has_cause = bool(re.search(r"cause of death|blame:|because|killed by|struck by|fell to|slain by|(?:goblin|captain|collapse|poison|wound|trap)", death, re.I))
        has_retry = bool(re.search(r"retry hint:|retry:|try again|next time|start over|return to", death, re.I))
        if not has_cause and not has_retry:
            _add(out, "FAIL_WITH_NOTHING", row, death.strip(), "Death screen names neither a cause nor a retry hint.")

    if receipt and receipt.get("stop_reason") == "no_progress":
        out.append(_instance("STALLED_RUN", [], "", "Controller run receipt stopped for no_progress.",
            artifact={"probe_version": 1, "run_receipt": receipt}))

    out.extend(probe_delve_static())
    latency = probe_latency()
    if latency["p95_ns"] >= 100_000_000:
        out.append(_instance("LATENCY_BREAK", [], "", f"Scripted Delve replay p95 was {latency['p95_ns']/1e6:.1f}ms/action.", artifact=latency))
    out.probe_artifacts.append({"kind": "latency_measurement", **latency})
    return out


def session_facts_delve(records):
    rooms, clues, facts, callbacks = set(), set(), set(), 0
    earned = 0
    callback_terms = re.compile(r"remember|recognizes|as before|again|still carries|you gave|your earlier|what you learned|wants it filled", re.I)
    for i, row in enumerate(records):
        after = row.get("snapshot", {})
        rooms.add(after.get("room_id"))
        clues.update(after.get("known_clues", [])); facts.update(after.get("known_facts", []))
        if i and _is_action(row) and callback_terms.search(row.get("new_output", "")):
            before = records[i-1].get("snapshot", {})
            text = row.get("new_output", "").casefold()
            prior_values = list(before.get("inventory", [])) + list(before.get("known_clues", []))
            prior_values += list(before.get("known_facts", [])) + list(before.get("flags", []))
            markers = [str(value).replace("_", " ").casefold() for value in prior_values if value]
            if any(marker in text for marker in markers):
                callbacks += 1
        if i and _is_action(row) and _state_hash(row) and _state_hash(row) != _state_hash(records[i-1]):
            before = records[i-1].get("snapshot", {})
            durable_fields = ("inventory", "flags", "known_clues", "known_facts", "enemies", "clocks", "present_objects", "terminal")
            changed = [key for key in durable_fields if before.get(key) != after.get(key)]
            persists = any(any(future.get("snapshot", {}).get(key) == after.get(key)
                               for future in records[i+1:]) for key in changed)
            if changed and persists:
                earned += 1
    rooms.discard(None)
    actions = count_turns(records)
    counts = {"DISCOVERY": len(rooms), "CLUE_FOUND": len(clues), "FACT_LEARNED": len(facts),
              "EARNED_CONSEQUENCE": earned, "CALLBACK": callbacks}
    return {**counts, "curiosity_rates_per_100_actions": {k: 100 * v / actions if actions else 0.0 for k, v in counts.items()},
            "rooms_visited": len(rooms), "distinct_clues": len(clues), "distinct_facts": len(facts),
            "turns": actions, "attack_share": _attack_share(records)}


def curiosity_events_delve(records):
    return session_facts_delve(records)


def _attack_share(records):
    decisions = _combat_decisions(records)
    attack_verbs = {"a", "attack", "hit", "strike", "fight", "swing", "slash", "heavy"}
    return sum(r["input_calls"][0].strip().casefold() in attack_verbs for r in decisions) / len(decisions) if decisions else 0.0


def probe_delve_static():
    """Audit pack readers, clue reachability, and flags using loaded pack data."""
    _, pack = _bank_entries()
    out = []
    readers = [obj for room in pack.rooms for obj in room.objects if obj.reader]
    clue_events = {clue.event_key for clue in pack.clues}
    for obj in readers:
        if not obj.reader.effects and obj.reader.event_key not in clue_events:
            out.append(_instance("INERT_OBJECT", [], "", f"Reader on {obj.name} has no effect or clue purpose.",
                artifact={"probe_version": 1, "object_id": obj.id, "event_key": obj.reader.event_key}))
    bank = {entry.key for entry in pack.bank}
    for clue in pack.clues:
        source_obj = next((obj for room in pack.rooms for obj in room.objects if obj.id == clue.source_id), None)
        source_item = next((item for item in pack.items if item.id == clue.source_id), None)
        reader = source_obj.reader if source_obj else (source_item.reader if source_item else None)
        reveals_clue = bool(reader and any(eff.type == "reveal_clue" and eff.clue_id == clue.id for eff in reader.effects))
        if clue.event_key not in bank or not reveals_clue:
            out.append(_instance("UNREADABLE_CLUE", [], "", f"Clue {clue.id} lacks a bank line or reachable reader.",
                artifact={"probe_version": 1, "clue_id": clue.id, "event_key": clue.event_key,
                          "source_id": clue.source_id, "reader_event_key": reader.event_key if reader else None,
                          "bank_keys": sorted(bank)}))
    read_flags = {exit.gate.flag_id for room in pack.rooms for exit in room.exits if exit.gate}
    effects = [eff for room in pack.rooms for obj in room.objects if obj.reader for eff in obj.reader.effects]
    effects += [eff for item in pack.items for eff in item.reader.effects]
    read_flags.update(eff.flag_id for eff in effects if getattr(eff, "type", "") == "require_flag")
    read_flags.update(obj.reader.when_flag_id for room in pack.rooms for obj in room.objects
                      if obj.reader and obj.reader.when_flag_id)
    read_flags.update(item.reader.when_flag_id for item in pack.items if item.reader.when_flag_id)
    read_flags.update(predicate["flag_id"] for terminal in pack.terminals for predicate in terminal.all
                      if predicate.get("kind") == "flag_set")
    written = {eff.flag_id for eff in effects if getattr(eff, "type", "") == "set_flag"}
    for flag in sorted(written - read_flags):
        out.append(_instance("UNREAD_FLAG", [], "", f"Flag {flag} is written but no exit or effect reads it.",
            artifact={"probe_version": 1, "flag": flag, "written_flags": sorted(written), "read_flags": sorted(read_flags)}))
    return out


def probe_latency():
    """Record per-action p95 over 100 timed actions on the real replay harness."""
    from .harness import replay
    from .schema import count_turns
    errors = []
    # One real replay, instrumenting the built-in input calls used by the harness.
    # Time each authoritative action in the real 100-action harness replay.
    from delve.engine import Engine
    real_apply = Engine.apply
    samples = []
    def timed_apply(engine, action):
        started = time.perf_counter_ns()
        try:
            return real_apply(engine, action)
        finally:
            samples.append(time.perf_counter_ns() - started)
    started = time.perf_counter_ns()
    with patch.object(Engine, "apply", timed_apply):
        result = replay(911, ["f"] + ["?"] * 100, game_id="delve")
    total = time.perf_counter_ns() - started
    actions = count_turns([{"frame_kind": "action"}] * 100)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, int(.95 * len(ordered)) - 1))] if ordered else total
    if result.error: errors.append(result.error)
    return {"probe_version": 1, "replay_seed": 911, "scripted_actions": actions,
            "elapsed_ns": total, "measured_actions": len(samples), "p95_ns": p95,
            "replay_error": errors or None, "measurement": "Engine.apply action latency in replay"}


def input_tax_probe():
    """Return the four real D&D pilot transcripts used to show command tax."""
    from pathlib import Path
    from .transcript import load_transcript
    root = Path(__file__).resolve().parent / "fixtures" / "real"
    return {path.parent.name: load_transcript(path) for path in sorted(root.glob("*/transcript.jsonl"))}
