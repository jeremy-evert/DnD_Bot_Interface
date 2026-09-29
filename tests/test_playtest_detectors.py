import json
from pathlib import Path
import unittest

from dnd_combat.world import make_dungeon
from playtest import fixtures
from playtest.detectors import curiosity_events, run_all, session_facts, verify_instance_quotes
from playtest.schema import count_turns
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

    def test_repeated_response_after_material_state_change_is_not_stall(self):
        rows = fixtures.repeated_response_after_state_change_real_harness()
        modes = {x["mode"] for x in run_all(rows)}
        self.assertNotIn("REPEATED_RESPONSE", modes)

    def test_repeated_response_requires_three_distinct_frames(self):
        rows = fixtures.repeated_response()
        for row in rows:
            row["frame_id"] = 17
        self.assertNotIn("REPEATED_RESPONSE", {x["mode"] for x in run_all(rows)})

    def test_repeated_response_requires_known_canonical_state(self):
        rows = fixtures.repeated_response()
        for row in rows:
            row["snapshot"].pop("canonical_state_hash")
        self.assertNotIn("REPEATED_RESPONSE", {x["mode"] for x in run_all(rows)})

    def test_informative_accepted_action_is_not_stall(self):
        rows = fixtures.informative_action_real_harness()
        modes = {x["mode"] for x in run_all(rows)}
        self.assertIn("I can open a way west", rows[-1]["new_output"])
        self.assertEqual(rows[-2]["snapshot"]["canonical_state_hash"],
                         rows[-1]["snapshot"]["canonical_state_hash"])
        self.assertNotIn("NO_CONSEQUENCE_STALL", modes)

    def test_informative_look_is_not_stall(self):
        rows = fixtures.informative_look_real_harness()
        look = next(r for r in rows if r["input_calls"] == ["look"])
        self.assertTrue(any(word in look["new_output"].lower()
                            for word in ("exits:", "you see:", "portrait")))
        self.assertNotIn("NO_CONSEQUENCE_STALL", {x["mode"] for x in run_all(rows)})

    def test_no_consequence_stall(self):
        self.assert_fires("NO_CONSEQUENCE_STALL", fixtures.no_consequence_stall(), "You wait.")
        state = {"room_id": "entry", "canonical_state_hash": "same"}
        refused_rows = fixtures._records(
            ["Ready.", "Choose move, look, status, take, use, or talk."],
            [[], ["nonsense"]], [state, state])
        refused = run_all(refused_rows)
        self.assertNotIn("NO_CONSEQUENCE_STALL", {x["mode"] for x in refused})

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

    def test_death_detection_uses_state_and_structural_terminal_message(self):
        for wording in ("You die. The adventure ends here.",
                        "Your journey stops here.",
                        "The last light goes out."):
            rows = fixtures.death_wording_real_harness(wording)
            self.assertIn("FAIL_WITH_NOTHING", {x["mode"] for x in run_all(rows)})
        for wording in ("The captain killed you because you ignored the warning.",
                        "Fall here, then try again next time with a shield.",
                        "Your friends carry the map onward beyond the gates.",
                        "The campaign ends before you can learn what waited beyond the sealed gate."):
            rows = fixtures.death_wording_real_harness(wording)
            self.assertNotIn("FAIL_WITH_NOTHING", {x["mode"] for x in run_all(rows)})

    def test_long_empty_death_fires_and_unknown_death_is_inconclusive(self):
        empty = fixtures.death_wording_real_harness(
            "The story ends. Silence follows. Darkness fills the hall.")
        self.assertIn("FAIL_WITH_NOTHING", {x["mode"] for x in run_all(empty)})
        informative = (
            "The captain was killed by a trap.",
            "The adventure ends here. Try again with a shield.",
            "Your friends carry the map onward beyond the gates.",
        )
        for wording in informative:
            with self.subTest(wording=wording):
                clean = fixtures.death_wording_real_harness(wording)
                results = run_all(clean)
                self.assertNotIn("FAIL_WITH_NOTHING", {x["mode"] for x in results})
                self.assertFalse(results.notes, wording)
        unknown = run_all(fixtures.death_wording_real_harness(
            "A blue moth circles the seventh arch before dawn."))
        self.assertNotIn("FAIL_WITH_NOTHING", {x["mode"] for x in unknown})
        self.assertTrue(any(note["mode"] == "INCONCLUSIVE" for note in unknown.notes))

    def test_real_harness_provenance_table_executes_every_twin(self):
        expected = {"repeated_response_real_harness", "no_consequence_stall_real_harness",
                    "hollow_consequence_real_harness", "world_state_contradiction_real_harness",
                    "death_wording_real_harness_twin"}
        self.assertEqual({twin for _, twin, _ in fixtures.REAL_HARNESS_PROVENANCE}, expected)
        evidence = {}
        for label, twin_name, mode in fixtures.REAL_HARNESS_PROVENANCE:
            with self.subTest(twin=label):
                rows = getattr(fixtures, twin_name)()
                self.assertTrue(rows)
                self.assertTrue(all("canonical_state_hash" in r["snapshot"] for r in rows))
                self.assertIn(mode, {item["mode"] for item in run_all(rows)})
                evidence[label] = rows
        repeated = evidence["repeated response"][-3:]
        self.assertEqual([r["snapshot"]["room_id"] for r in repeated], ["gallery"] * 3)
        self.assertEqual(len({r["snapshot"]["canonical_state_hash"] for r in repeated}), 1)
        stall = evidence["no-consequence action"][-2:]
        self.assertEqual([r["snapshot"]["room_id"] for r in stall], ["gallery"] * 2)
        self.assertTrue(stall[0]["snapshot"]["vault_opened"])
        self.assertIn("remains open", stall[-1]["new_output"])
        self.assertEqual(stall[0]["snapshot"]["canonical_state_hash"],
                         stall[1]["snapshot"]["canonical_state_hash"])
        self.assertIn("goblin's brass ring", evidence["hollow consequence"][-1]["snapshot"]["inventory"])
        before, after = evidence["hollow consequence"][-2:]
        self.assertEqual(before["snapshot"]["room_id"], "gallery")
        self.assertFalse(before["snapshot"]["vault_opened"])
        self.assertEqual(after["snapshot"]["room_id"], "gallery")
        self.assertTrue(after["snapshot"]["vault_opened"])
        self.assertEqual(after["snapshot"]["rooms"]["gallery"]["exits"]["west"], "sanctum")
        contradiction = evidence["world-state contradiction"][-1]["snapshot"]
        self.assertEqual(contradiction["room_id"], "shrine")
        self.assertEqual(contradiction["rooms"]["shrine"]["exits"]["east"], "sanctum")
        death = evidence["death wording"][-1]
        self.assertEqual(death["snapshot"]["game_state"], "dead")
        self.assertIn("You have fallen. The adventure ends here.", death["new_output"])

    def test_death_terminal_message_follows_last_combat_resolution(self):
        rows = fixtures.death_wording(
            "Your story ends.",
            prefix="Earlier cause: a trap.\nHero rolls 4 (1) and misses Goblin.\n")
        self.assertIn("FAIL_WITH_NOTHING", {x["mode"] for x in run_all(rows)})

    def test_noise_cases_on_real_transcripts(self):
        cases = fixtures.real_noise_cases()
        self.assertEqual(set(cases), {"combat_extra_input", "full_hp_potion"})
        extra = {x["mode"] for x in run_all(cases["combat_extra_input"])}
        potion = {x["mode"] for x in run_all(cases["full_hp_potion"])}
        # This pilot frame really is an invalid extra combat input and should fire.
        self.assertIn("UNRECOGNIZED_COMMAND", extra)
        self.assertNotIn("NO_CONSEQUENCE_STALL", potion)

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
            # Annabelle action-count clause: setup record is excluded from every rate denominator.
            self.assertEqual(session_facts(records)["turns"], count_turns(records))
            self.assertEqual(curiosity_events(records)["turns"], count_turns(records))
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
