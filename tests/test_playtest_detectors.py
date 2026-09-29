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
    source = "\n".join(p.read_text() for p in (ROOT / "dnd_combat").glob("*.py") if p.name != "world.py")
    inert = []
    for room in make_dungeon().values():
        for obj in room.objects:
            if obj.takeable and obj.name.lower() not in source.lower() and not any(a.lower() in source.lower() for a in obj.aliases):
                inert.append(obj.name)
    return {"inert_takeables": inert}


class DetectorTests(unittest.TestCase):
    def assert_fires(self, mode, records, quote, journal=None):
        items = [x for x in run_all(records, journal) if x["mode"] == mode]
        self.assertTrue(items, mode)
        self.assertTrue(any(quote in r["new_output"] for r in records))
        self.assertEqual(items[0]["quote"], quote)
        self.assertTrue(verify_instance_quotes(records, items))

    def test_unrecognized_command(self):
        self.assert_fires("UNRECOGNIZED_COMMAND", fixtures.unrecognized_command(), "Choose move, look, status, take, use, or talk.")

    def test_unsupported_intent(self):
        self.assert_fires("UNSUPPORTED_INTENT", fixtures.unsupported_intent(), "There is no one here to talk to.",
                          [{"turn_id": 0, "unsupported_intent": "talk to rock"}])

    def test_repeated_response(self):
        self.assert_fires("REPEATED_RESPONSE", fixtures.repeated_response(), "That does nothing.")

    def test_no_consequence_stall(self):
        self.assert_fires("NO_CONSEQUENCE_STALL", fixtures.no_consequence_stall(), "You wait.")

    def test_hollow_consequence(self):
        self.assert_fires("HOLLOW_CONSEQUENCE", fixtures.hollow_consequence(), "Mira opens the hidden door west.")

    def test_world_state_contradiction(self):
        self.assert_fires("WORLD_STATE_CONTRADICTION", fixtures.world_state_contradiction(), "Rootbound Shrine: The sealed vault waits east.")

    def test_dominant_action_modes_and_share(self):
        rows = fixtures.dominant_action()
        modes = {x["mode"] for x in run_all(rows)}
        self.assertTrue({"DOMINANT_ACTION", "DOMINANT_ACTION_SOFT"} <= modes)
        self.assertTrue(verify_instance_quotes(rows, [x for x in run_all(rows) if x["mode"].startswith("DOMINANT_ACTION")]))
        self.assertEqual(session_facts(rows)["attack_share"], 1.0)
        self.assertEqual(session_facts(rows)["hero_combat_decisions"], 5)

    def test_dominant_action_soft_boundary(self):
        rows = fixtures.dominant_action()
        # Four attack decisions and one potion decision, using real combat text.
        rows = fixtures._records([r["new_output"] for r in rows], [["attack"]] * 4 + [["use", "potion"]])
        modes = {x["mode"] for x in run_all(rows)}
        self.assertIn("DOMINANT_ACTION_SOFT", modes)
        self.assertNotIn("DOMINANT_ACTION", modes)

    def test_fail_with_nothing_and_clean_death(self):
        records = fixtures.fail_with_nothing()
        self.assert_fires("FAIL_WITH_NOTHING", records, "You have fallen. The adventure ends here.")
        clean = fixtures.clean_death()
        self.assertNotIn("FAIL_WITH_NOTHING", {x["mode"] for x in run_all(clean)})

    def test_convention_clash(self):
        rows = fixtures.clean_route()
        item = next(x for x in run_all(rows) if x["mode"] == "CONVENTION_CLASH")
        self.assertEqual(item["quote"], "Probe the Fighter:")
        self.assertTrue(verify_instance_quotes(rows, [item]))

    def test_inert_takeable(self):
        item = next(x for x in run_all(fixtures.clean_route(), content=inert_content()) if x["mode"] == "INERT_TAKEABLE")
        self.assertEqual(item["turn_ids"], [])
        self.assertEqual(item["quote"], "")

    def test_real_pilot_regressions_and_receipt(self):
        names = ["pilot1_explorer", "pilot2_tactician", "pilot3_rules_lawyer", "pilot4_newcomer"]
        modes = ["CONVENTION_CLASH", "DOMINANT_ACTION", "DOMINANT_ACTION_SOFT", "FAIL_WITH_NOTHING",
                 "HOLLOW_CONSEQUENCE", "INERT_TAKEABLE", "NO_CONSEQUENCE_STALL", "REPEATED_RESPONSE",
                 "UNRECOGNIZED_COMMAND", "UNSUPPORTED_INTENT", "WORLD_STATE_CONTRADICTION"]
        table, shares = {}, {}
        for name in names:
            folder = REAL / name
            records = load_transcript(folder / "transcript.jsonl")
            items = run_all(records, journal_for(folder), inert_content())
            table[name] = {mode: sum(x["mode"] == mode for x in items) for mode in modes}
            shares[name] = session_facts(records)["attack_share"]
            self.assertTrue(verify_instance_quotes(records, [x for x in items if x["turn_ids"]]))
            self.assertEqual(session_facts(records)["turns"], len(records))
            self.assertEqual(curiosity_events(records)["turns"], len(records))
        expected = {
            "pilot1_explorer": [1, 0, 1, 0, 0, 5, 0, 0, 2, 0, 1],
            "pilot2_tactician": [1, 0, 1, 0, 0, 5, 0, 0, 2, 1, 2],
            "pilot3_rules_lawyer": [1, 0, 1, 0, 1, 5, 0, 0, 4, 4, 1],
            "pilot4_newcomer": [1, 0, 1, 1, 1, 5, 0, 0, 3, 0, 1],
        }
        for name in names:
            self.assertEqual([table[name][mode] for mode in modes], expected[name], name)
        self.assertEqual([shares[n] for n in names], [5/6, 5/6, 4/5, 6/7])
        self.assertIn("You have fallen. The adventure ends here.", load_transcript(REAL / "pilot4_newcomer" / "transcript.jsonl")[-1]["new_output"])
        print("\nReal pilot detector counts (" + " | ".join(modes) + ")")
        for name in names:
            print(name + " | " + " | ".join(str(table[name][m]) for m in modes) + f" | attack_share={shares[name]:.4f}")

    def test_deterministic_non_mutating_and_quote_mutation_guard(self):
        records = fixtures.unrecognized_command()
        original = json.dumps(records, sort_keys=True)
        first, second = run_all(records), run_all(records)
        self.assertEqual(first, second)
        self.assertEqual(original, json.dumps(records, sort_keys=True))
        first[0]["quote"] = "fabricated"
        with self.assertRaises(ValueError):
            verify_instance_quotes(records, first)


if __name__ == "__main__":
    unittest.main()
