"""Delve detector contract, real pilot baselines, and controlled twins."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from playtest import fixtures_delve as fixtures
from playtest.detectors import run_all, verify_instance_quotes
from playtest.detectors_delve import (DETECTOR_VERSION_DELVE, input_tax_probe,
    BOOKKEEPING_SNAPSHOT_FIELDS, MATERIAL_SNAPSHOT_FIELDS, NOT_A_REFUSAL, REFUSAL_KEYS,
    _is_refusal, material_state, probe_delve_static, refusal_templates,
    run_all_delve, session_facts_delve)
from playtest.schema import SEVERITY_TAXONOMY, count_turns
from playtest.transcript import load_transcript

ROOT = Path(__file__).resolve().parents[1]
REAL_MODES = ("UNRECOGNIZED_COMMAND", "UNSUPPORTED_INTENT", "REPEATED_RESPONSE",
              "NO_CONSEQUENCE_STALL", "DOMINANT_ACTION", "DOMINANT_ACTION_SOFT",
              "MISSING_TELEGRAPH", "FAIL_WITH_NOTHING", "INPUT_TAX", "STALLED_RUN",
              "UNSIGNALED_DEAD_END", "INERT_OBJECT", "UNREADABLE_CLUE", "UNREAD_FLAG", "LATENCY_BREAK")


def copy_row(row):
    return json.loads(json.dumps(row))


def repeat_twin(records):
    source = next(r for r in records if r.get("input_calls") and r["input_calls"][0] == "?")
    rows = []
    for number in range(3):
        row = copy_row(source)
        row["turn_id"] = number + 1; row["frame_id"] = number + 1
        row["frame_kind"] = "action"; row["snapshot"]["canonical_state_hash"] = "stable-state"
        row["new_output"] = "You read the same route warning from the wall."
        rows.append(row)
    return rows


def dominant_twin(records):
    candidates = [r for r in records if r.get("input_calls") and
                  ("Solid hit:" in r.get("new_output", "") or "A miss." in r.get("new_output", ""))]
    rows = []
    for number in range(5):
        row = copy_row(candidates[number % len(candidates)])
        row["turn_id"] = number + 1; row["frame_id"] = number + 1; row["frame_kind"] = "action"
        row["input_calls"] = ["attack"]
        row["snapshot"]["canonical_state_hash"] = f"combat-state-{number}"
        rows.append(row)
    return rows


class DelveDetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = fixtures.real_sessions()

    def modes(self, rows, **kwargs):
        return [item["mode"] for item in run_all_delve(rows, **kwargs)]

    def test_frozen_taxonomy_and_versions(self):
        expected = {"UNRECOGNIZED_COMMAND": 2, "UNSUPPORTED_INTENT": 3,
            "REPEATED_RESPONSE": 3, "NO_CONSEQUENCE_STALL": 4,
            "DOMINANT_ACTION": 3, "DOMINANT_ACTION_SOFT": 1,
            "MISSING_TELEGRAPH": 5, "FAIL_WITH_NOTHING": 3,
            "INPUT_TAX": 2, "STALLED_RUN": 3, "UNSIGNALED_DEAD_END": 4,
            "INERT_OBJECT": 2, "UNREADABLE_CLUE": 4, "UNREAD_FLAG": 2,
            "LATENCY_BREAK": 4}
        self.assertEqual({mode: SEVERITY_TAXONOMY[mode] for mode in expected}, expected)
        self.assertEqual(DETECTOR_VERSION_DELVE, "delve-1")

    def test_real_pilot_provenance_and_clean_telegraph_and_input_tax(self):
        self.assertEqual(len(self.sessions), 12)
        for name, session in self.sessions.items():
            with self.subTest(session=name):
                records = session["records"]
                self.assertEqual(records[0]["frame_kind"], "setup")
                self.assertEqual(count_turns(records), len(records) - 1)
                results = run_all_delve(records, session["journal"], receipt=session["receipt"])
                self.assertTrue(verify_instance_quotes(records, results))
                self.assertNotIn("MISSING_TELEGRAPH", [i["mode"] for i in results])
                self.assertNotIn("INPUT_TAX", [i["mode"] for i in results])
                self.assertNotIn("FAIL_WITH_NOTHING", [i["mode"] for i in results])
                self.assertNotIn("UNSIGNALED_DEAD_END", [i["mode"] for i in results])

    def test_real_delve_expected_per_mode_counts(self):
        modes = ("UNRECOGNIZED_COMMAND", "UNSUPPORTED_INTENT", "REPEATED_RESPONSE",
                 "NO_CONSEQUENCE_STALL", "DOMINANT_ACTION", "DOMINANT_ACTION_SOFT",
                 "MISSING_TELEGRAPH", "FAIL_WITH_NOTHING", "INPUT_TAX", "STALLED_RUN",
                 "UNSIGNALED_DEAD_END")
        expected = {
            # The historical banks recover refusals missed by the old current-bank matcher.
            "delve2_explorer": [5, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "delve2_newcomer": [4, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "delve2_rules_lawyer": [7, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "delve2_tactician": [8, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "delve3_explorer": [6, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "delve3_newcomer": [4, 3, 0, 0, 0, 0, 0, 0, 0, 1, 0],
            "delve3_rules_lawyer": [10, 9, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "delve3_tactician": [4, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "delve_explorer": [5, 3, 0, 0, 0, 0, 0, 0, 0, 1, 0],
            "delve_newcomer": [10, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "delve_rules_lawyer": [7, 5, 0, 0, 0, 0, 0, 0, 0, 1, 0],
            "delve_tactician": [9, 9, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        }
        before_stalls = {name: int(name in {"delve2_explorer", "delve3_explorer"}) for name in expected}
        table = {}
        for name, session in self.sessions.items():
            results = run_all_delve(session["records"], session["journal"], receipt=session["receipt"])
            table[name] = [sum(bool(item["mode"] == mode and item["turn_ids"]) for item in results) if mode != "STALLED_RUN"
                           else sum(item["mode"] == mode for item in results) for mode in modes]
            self.assertEqual(table[name], expected[name], name)
        before = {name: list(values) for name, values in table.items()}
        for name, count in before_stalls.items():
            before[name][3] = count
        print("\nReal Delve per-mode counts BEFORE -> AFTER (" + " | ".join(modes) + ")")
        for name in sorted(table):
            print(name + " | " + " | ".join(str(value) for value in before[name]) +
                  " -> " + " | ".join(str(value) for value in table[name]))

    def test_unrecognized_unsupported_from_real_harness_refusal(self):
        result, rows = fixtures.real_delve_run(["give ring to Mira"])
        from delve.pack import load_engine_ready_pack
        pack = load_engine_ready_pack(ROOT / "delve" / "content" / "mossy_fast_slice.json")
        quote = next(line for line in result.output.splitlines()
                     if any(pattern.match(line.strip()) for pattern in refusal_templates(pack)))
        self.assertIn("UNRECOGNIZED_COMMAND", self.modes(rows))
        journal = [{"turn_id": 1, "unsupported_intent": "give ring to Mira"}]
        self.assertIn("UNSUPPORTED_INTENT", self.modes(rows, journal=journal))
        self.assertTrue(verify_instance_quotes(rows, run_all_delve(rows, journal=journal)))
        # Journal claim without an output refusal is insufficient.
        row = copy_row(rows[-1]); row["new_output"] = "You find the ring."; row["snapshot"]["canonical_state_hash"] = "changed"
        self.assertNotIn("UNSUPPORTED_INTENT", self.modes([row], journal=journal))

    def test_refusal_classification_covers_current_bank(self):
        from delve.pack import load_engine_ready_pack
        pack = load_engine_ready_pack(ROOT / "delve" / "content" / "mossy_fast_slice.json")
        bank_keys = {entry.key for entry in pack.bank}
        self.assertEqual(bank_keys, REFUSAL_KEYS | set(NOT_A_REFUSAL))
        self.assertFalse(REFUSAL_KEYS & set(NOT_A_REFUSAL))
        self.assertTrue(all(NOT_A_REFUSAL.values()))

    def test_refusal_templates_follow_new_keys_and_wording_drift(self):
        import copy
        from delve.pack import load_engine_ready_pack
        from playtest import detectors_delve
        source = json.loads((ROOT / "delve" / "content" / "mossy_fast_slice.json").read_text(encoding="utf-8"))
        templates = refusal_templates(source)
        for key in sorted(REFUSAL_KEYS):
            entry = next(row for row in source["bank"]["entries"] if row["key"] == key)
            for index, variant in enumerate(entry["variants"]):
                rendered = variant.replace("{{target}}", "sample target").replace("{{candidates}}", "sample A, sample B")
                rendered = rendered.replace("{{enemy_name}}", "sample foe").replace("{{direction}}", "north")
                rendered = rendered.replace("{{object_name}}", "sample object").replace("{{verb}}", "sample verb")
                self.assertTrue(any(pattern.match(rendered) for pattern in templates), (key, index, rendered))

        # A classification decision adds a new refusal key; template extraction
        # then discovers its variants from pack data without detector edits.
        mutated = copy.deepcopy(source)
        mutated["bank"]["entries"].append({"key": "target.new_refusal", "variants": ["The {{target}} is beyond reach!"], "fallback": "The {{target}} is beyond reach!"})
        with patch.object(detectors_delve, "REFUSAL_KEYS", REFUSAL_KEYS | {"target.new_refusal"}):
            added = refusal_templates(mutated)
        self.assertTrue(any(pattern.match("The sample target is beyond reach!") for pattern in added))

        # Content mutation is also data only: altered static wording still matches.
        changed = copy.deepcopy(source)
        changed_entry = next(row for row in changed["bank"]["entries"] if row["key"] == "parse.unknown_verb")
        changed_entry["variants"][0] = "Fresh rejection for {{verb}}!"
        changed_templates = refusal_templates(changed)
        self.assertTrue(_is_refusal("Fresh rejection for moonwalking!", changed_templates))

    def test_unmatched_game_build_is_inconclusive(self):
        row = fixtures.action_row(1, ["mystery"], "A response with no known refusal template.", {})
        row["game_sha"] = "unknown-build-sha"
        found = run_all_delve([row])
        self.assertTrue(any(note.get("kind") == "INCONCLUSIVE"
                            and note.get("mode") == "UNRECOGNIZED_COMMAND"
                            and note.get("rationale") == "refusal templates unavailable for this build"
                            for note in found.notes))

    def test_m114_wording_refusals_from_fresh_real_replays(self):
        from playtest.harness import replay
        absent = replay(0, ["f", "x nobody"], game_id="delve")
        self.assertIsNone(absent.error)
        absent_row = fixtures.action_row(1, ["x nobody"], absent.output, {})
        self.assertIn("isn’t here", absent.output)
        self.assertIn("UNRECOGNIZED_COMMAND", self.modes([absent_row]))

        not_held = replay(731, ["f", "use ring"], game_id="delve")
        self.assertIsNone(not_held.error)
        not_held_row = fixtures.action_row(1, ["use ring"], not_held.output, {})
        self.assertIn("not in hand", not_held.output)
        self.assertIn("UNRECOGNIZED_COMMAND", self.modes([not_held_row]))

    def test_throw_fizzle_remains_a_consequence_not_a_refusal(self):
        self.assertNotIn("throw.fizzle", REFUSAL_KEYS)
        self.assertIn("Consequence", NOT_A_REFUSAL["throw.fizzle"])

    def test_repeated_response_twin_and_state_epoch_guard(self):
        source = self.sessions["delve_explorer"]["records"]
        rows = repeat_twin(source)
        self.assertIn("REPEATED_RESPONSE", self.modes(rows))
        rows[2]["snapshot"]["player"] = {"hp": 1}
        self.assertNotIn("REPEATED_RESPONSE", self.modes(rows))

    def test_snapshot_fields_are_exhaustively_classified(self):
        from delve.state import DelveState
        from delve.pack import load_engine_ready_pack
        snapshot = DelveState.new(load_engine_ready_pack(ROOT / "delve" / "content" / "mossy_fast_slice.json"), 3, "fighter").snapshot()
        self.assertEqual(set(snapshot), MATERIAL_SNAPSHOT_FIELDS | BOOKKEEPING_SNAPSHOT_FIELDS)
        self.assertEqual(set(material_state(snapshot)), MATERIAL_SNAPSHOT_FIELDS)
        snapshot["new_future_counter"] = 1
        with self.assertRaisesRegex(ValueError, "unclassified Delve snapshot fields"):
            material_state(snapshot)

    def test_real_controller_stall_and_repeat_twin(self):
        result, twin = fixtures.stall_twin()
        self.assertIsNone(result.error)
        found = run_all_delve(twin)
        self.assertIn("NO_CONSEQUENCE_STALL", [item["mode"] for item in found])
        self.assertIn("REPEATED_RESPONSE", [item["mode"] for item in found])
        for session in self.sessions.values():
            modes = self.modes(session["records"], journal=session["journal"])
            self.assertNotIn("NO_CONSEQUENCE_STALL", modes)
            self.assertNotIn("REPEATED_RESPONSE", modes)

    def test_stall_and_combat_resolution_rules_on_real_rows(self):
        # This synthetic pair remains usable even when historical content adds
        # newly recognized refusals to the real transcript corpus.
        state = {"canonical_state_hash": "same"}
        rows = [fixtures.action_row(0, [], "MOSSY ENTRY", state, frame_kind="setup")]
        rows.extend(fixtures.action_row(turn, ["wait"], "You wait.", state) for turn in (1, 2, 3))
        self.assertIn("NO_CONSEQUENCE_STALL", self.modes(rows))
        # A combat resolution is a consequence even when canonical state did not change.
        state = copy_row(rows[-1]["snapshot"]); state["canonical_state_hash"] = "same"
        prior = {"turn_id": 80, "frame_id": 80, "frame_kind": "action", "input_calls": ["a"],
                 "new_output": "Solid hit: 1 into the Goblin.", "snapshot": state}
        after = copy_row(prior); after["turn_id"] = after["frame_id"] = 81
        after["new_output"] = "A miss. The Goblin resets."
        self.assertNotIn("NO_CONSEQUENCE_STALL", self.modes([prior, after]))

    def test_queries_and_refusals_are_excluded_from_stall(self):
        state = {"canonical_state_hash": "same"}
        for command, output in ((["x collapse"], "You inspect the collapse."),
                                (["i"], "Inventory: empty."),
                                (["?"], "Commands are listed."),
                                (["q"], "Goodbye.")):
            rows = [fixtures.action_row(0, [], "Setup", state, frame_kind="setup")]
            rows.extend(fixtures.action_row(turn, command, output, state) for turn in (1, 2, 3))
            self.assertNotIn("NO_CONSEQUENCE_STALL", self.modes(rows), command)
        refusal = next(row for session in self.sessions.values() for row in session["records"]
                       if row.get("input_calls") and any(item["mode"] == "UNRECOGNIZED_COMMAND"
                           and item["turn_ids"] == [row["turn_id"]]
                           for item in run_all_delve(session["records"], session["journal"])))
        rows = [copy_row(refusal) for _ in range(3)]
        for turn, row in enumerate(rows, 1): row["turn_id"] = row["frame_id"] = turn
        self.assertNotIn("NO_CONSEQUENCE_STALL", self.modes(rows))

    def test_dominant_action_twin_and_soft_boundary(self):
        source = self.sessions["delve3_newcomer"]["records"]
        rows = dominant_twin(source)
        found = [item for item in run_all_delve(rows) if item["mode"].startswith("DOMINANT_ACTION")]
        self.assertEqual({item["mode"] for item in found}, {"DOMINANT_ACTION", "DOMINANT_ACTION_SOFT"})
        facts = session_facts_delve(rows)
        self.assertEqual(facts["attack_share"], 1.0)
        self.assertEqual(facts["turns"], count_turns(rows))

    def test_missing_telegraph_output_twin(self):
        result, rows = fixtures.missing_telegraph_twin()
        self.assertIsNone(result.error)
        self.assertLess(rows[-1]["snapshot"]["player"]["hp"], rows[0]["snapshot"]["player"]["hp"])
        self.assertIn("MISSING_TELEGRAPH", self.modes(rows))
        self.assertTrue(verify_instance_quotes(rows, run_all_delve(rows)))

    def test_death_screen_failure_twin_and_clean_death_wording(self):
        result, rows = fixtures.fail_with_nothing_twin()
        row = rows[-1]
        self.assertIsNone(result.error)
        self.assertEqual(row["snapshot"]["terminal"], "dead")
        self.assertIn("YOU DIED — The dark takes you.", row["new_output"])
        self.assertIn("FAIL_WITH_NOTHING", self.modes(rows))
        # Shipped output includes a retry hint, even when its cause text varies.
        row = {"turn_id": 9, "frame_id": 9, "frame_kind": "action", "input_calls": ["a"],
               "termination": "dead", "new_output": "YOU DIED — The dark takes you.\nRetry hint: Try again with the warning in mind.",
               "snapshot": {"terminal": "dead", "canonical_state_hash": "dead"}}
        self.assertNotIn("FAIL_WITH_NOTHING", self.modes([row]))
        row["new_output"] = "YOU DIED — It is over."
        self.assertIn("FAIL_WITH_NOTHING", self.modes([row]))

    def test_input_tax_probe_uses_real_dnd_action_frames(self):
        sessions = input_tax_probe()
        self.assertEqual(set(sessions), {"pilot1_explorer", "pilot2_tactician", "pilot3_rules_lawyer", "pilot4_newcomer"})
        counts = {}
        for name, records in sessions.items():
            hits = [item for item in run_all_delve(records) if item["mode"] == "INPUT_TAX"]
            counts[name] = len(hits)
            self.assertTrue(hits, name)
            self.assertTrue(verify_instance_quotes(records, hits))
        self.assertEqual(counts, {"pilot1_explorer": 13, "pilot2_tactician": 22,
                                  "pilot3_rules_lawyer": 12, "pilot4_newcomer": 10})
        # Delve itself keeps this Doom-principle detector silent.
        for session in self.sessions.values():
            self.assertNotIn("INPUT_TAX", self.modes(session["records"]))
        print("\nReal D&D 0.6 input-tax probe counts: " + json.dumps(counts, sort_keys=True))

    def test_stalled_run_static_audits_and_explicit_dead_end_limit(self):
        stalled = self.sessions["delve_explorer"]
        found = run_all_delve(stalled["records"], receipt=stalled["receipt"])
        self.assertIn("STALLED_RUN", [item["mode"] for item in found])
        static = probe_delve_static()
        self.assertTrue({"INERT_OBJECT", "UNREAD_FLAG"} <= {item["mode"] for item in static})
        # Pack validation proves current clue source/read reachability; broken clue twin is covered by static probe.
        self.assertNotIn("UNREADABLE_CLUE", {item["mode"] for item in static})
        # A dead end is not decidable from the transcript schema: no legal-action transition graph is recorded.
        for session in self.sessions.values():
            self.assertNotIn("UNSIGNALED_DEAD_END", self.modes(session["records"]))

    def test_latency_probe_p95_threshold(self):
        # A latency regression twin uses the actual replay wrapper but injects a slow action clock.
        with patch("playtest.detectors_delve.probe_latency", return_value={
                "probe_version": 1, "replay_seed": 911, "scripted_actions": 100,
                "elapsed_ns": 10_000_000_000, "p95_ns": 100_000_000,
                "replay_error": None, "measurement": "injected slow replay twin"}):
            found = run_all_delve(self.sessions["delve_explorer"]["records"])
        self.assertIn("LATENCY_BREAK", [item["mode"] for item in found])

    def test_real_delve_static_latency_measurement_is_recorded(self):
        found = run_all_delve(self.sessions["delve_explorer"]["records"])
        measurements = found.probe_artifacts
        self.assertEqual(measurements[0]["kind"], "latency_measurement")
        self.assertEqual(measurements[0]["scripted_actions"], 100)
        self.assertLess(measurements[0]["p95_ns"], 100_000_000)


if __name__ == "__main__":
    unittest.main()
