import json
from pathlib import Path
import unittest

from dnd_combat.world import make_dungeon
from playtest import fixtures
from playtest.detectors import curiosity_events, run_all, session_facts, verify_instance_quotes
from playtest.transcript import load_transcript

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "playtest" / "fixtures" / "real"


def journal_for(folder):
    return [json.loads(line) for line in (folder / "journal.jsonl").read_text().splitlines()]


def inert_content():
    # Source audit, deliberately performed by the caller (run_all stays pure).
    source = "\n".join(p.read_text() for p in (ROOT / "dnd_combat").glob("*.py") if p.name != "world.py")
    inert = []
    for room in make_dungeon().values():
        for obj in room.objects:
            if obj.takeable and obj.name.lower() not in source.lower() and not any(a.lower() in source.lower() for a in obj.aliases):
                inert.append(obj.name)
    return {"inert_takeables": inert}


class DetectorTests(unittest.TestCase):
    def test_each_textual_bad_fixture_fires_its_mode_with_exact_citation(self):
        journals = {"UNSUPPORTED_INTENT": [{"turn_id": 0, "unsupported_intent": "talk to rock"}]}
        for mode, records in fixtures.all_broken().items():
            with self.subTest(mode=mode):
                items = run_all(records, journals.get(mode))
                matching = [item for item in items if item["mode"] == mode]
                self.assertTrue(matching)
                self.assertTrue(verify_instance_quotes(records, matching))

    def test_clean_route_and_current_static_defects(self):
        records = fixtures.clean_route()
        modes = {item["mode"] for item in run_all(records)}
        self.assertFalse(modes & {"UNRECOGNIZED_COMMAND", "UNSUPPORTED_INTENT", "REPEATED_RESPONSE", "NO_CONSEQUENCE_STALL", "WORLD_STATE_CONTRADICTION", "DOMINANT_ACTION", "FAIL_WITH_NOTHING"})
        self.assertIn("CONVENTION_CLASH", modes)
        static = run_all(records, content=inert_content())
        self.assertIn("INERT_TAKEABLE", {item["mode"] for item in static})
        current = fixtures.world_state_contradiction()
        self.assertIn("WORLD_STATE_CONTRADICTION", {item["mode"] for item in run_all(current)})
        truthful = fixtures._records(["Rootbound Shrine: An open vault lies east."], [["look"]],
            [{"room_id": "shrine", "rooms": {"shrine": {"name": "Rootbound Shrine", "exits": {"east": "sanctum"}}}, "canonical_state_hash": "x"}])
        self.assertNotIn("WORLD_STATE_CONTRADICTION", {item["mode"] for item in run_all(truthful)})

    def test_real_pilots_and_print_detector_noise(self):
        expected = {"pilot1_explorer": False, "pilot2_tactician": False,
                    "pilot3_rules_lawyer": True, "pilot4_newcomer": True}
        content = inert_content()
        table = {}
        for name, should_hollow in expected.items():
            folder = REAL / name
            records = load_transcript(folder / "transcript.jsonl")
            items = run_all(records, journal_for(folder), content)
            modes = [item["mode"] for item in items]
            table[name] = {mode: modes.count(mode) for mode in sorted(set(modes))}
            self.assertEqual("HOLLOW_CONSEQUENCE" in modes, should_hollow)
            self.assertIn("CONVENTION_CLASH", modes)
            self.assertIn("INERT_TAKEABLE", modes)
            if name == "pilot4_newcomer": self.assertIn("UNRECOGNIZED_COMMAND", modes)
            if any("sealed vault" in r["new_output"].lower() for r in records): self.assertIn("WORLD_STATE_CONTRADICTION", modes)
            verify_instance_quotes(records, [x for x in items if x["turn_ids"]])
            print("noise", name, [x for x in items if x["mode"] in {"NO_CONSEQUENCE_STALL", "REPEATED_RESPONSE"}])
            self.assertEqual(session_facts(records)["turns"], len(records))
            self.assertEqual(curiosity_events(records)["turns"], len(records))
        all_modes = sorted({mode for row in table.values() for mode in row})
        print("\nReal pilot detector counts")
        print("pilot | " + " | ".join(all_modes))
        for name, row in table.items():
            print(name + " | " + " | ".join(str(row.get(mode, 0)) for mode in all_modes))

    def test_deterministic_and_non_mutating_and_quote_guard(self):
        records = fixtures.unrecognized_command()
        original = json.dumps(records, sort_keys=True)
        first, second = run_all(records), run_all(records)
        self.assertEqual(first, second)
        self.assertEqual(original, json.dumps(records, sort_keys=True))
        first[0]["quote"] = "fabricated"
        with self.assertRaises(ValueError): verify_instance_quotes(records, first)


if __name__ == "__main__":
    unittest.main()
