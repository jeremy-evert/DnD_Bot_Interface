import copy
import json
import random
import re
import unittest
from pathlib import Path

from delve.pack import load_pack
from delve.state import DelveState, roll_die

SPEC = Path(__file__).parents[1] / "docs" / "DELVE_M1_SPEC.md"
TEXT = SPEC.read_text(encoding="utf-8")
EXAMPLE = json.loads(re.search(r"### Complete valid example\s*```json\s*(.*?)\s*```", TEXT, re.S).group(1))
PACK = load_pack(EXAMPLE)


class DelveStateTests(unittest.TestCase):
    def test_same_run_has_identical_canonical_json(self):
        a = DelveState.new(PACK, 42, "fighter")
        b = DelveState.new(PACK, 42, "fighter")
        self.assertEqual(json.dumps(a.snapshot(), sort_keys=True, separators=(",", ":")),
                         json.dumps(b.snapshot(), sort_keys=True, separators=(",", ":")))
        self.assertEqual(a.snapshot()["canonical_state_hash"], b.snapshot()["canonical_state_hash"])

    def test_snapshot_json_safe_without_rng_object(self):
        snap = DelveState.new(PACK, 9, "rogue").snapshot()
        self.assertNotIn("rng", snap)
        self.assertEqual(json.loads(json.dumps(snap)), snap)

    def test_global_random_state_is_untouched(self):
        before = random.getstate()
        state = DelveState.new(PACK, 10, "wizard")
        roll_die(state, 20)
        self.assertEqual(before, random.getstate())

    def test_global_seed_does_not_change_outputs(self):
        random.seed(1234)
        a = DelveState.new(PACK, 55, "fighter")
        result_a = [roll_die(a, 20) for _ in range(5)]
        random.seed(1234)
        b = DelveState.new(PACK, 55, "fighter")
        result_b = [roll_die(b, 20) for _ in range(5)]
        self.assertEqual(result_a, result_b)
        self.assertEqual(a.snapshot(), b.snapshot())

    def test_draw_accounting_and_seeded_streams(self):
        a, b = DelveState.new(PACK, 1, "fighter"), DelveState.new(PACK, 2, "fighter")
        self.assertEqual(a.rng_draws, 0)
        draws_a = [roll_die(a, 20) for _ in range(8)]
        draws_b = [roll_die(b, 20) for _ in range(8)]
        self.assertEqual(a.rng_draws, 8)
        self.assertEqual(b.rng_draws, 8)
        self.assertNotEqual(draws_a, draws_b)

    def test_hero_stats(self):
        expected = {
            "fighter": (24, 16, 5, 10, 3),
            "rogue": (18, 14, 5, 8, 3),
            "wizard": (14, 12, 5, 10, 2),
        }
        for hero, stats in expected.items():
            player = DelveState.new(PACK, 1, hero).player
            self.assertEqual(tuple(player[k] for k in ("max_hp", "armor_class", "attack_bonus", "damage_die", "damage_bonus")), stats)
            self.assertEqual(player["hp"], stats[0])
        with self.assertRaises(ValueError):
            DelveState.new(PACK, 1, "bard")

    def test_pack_world_initialisation(self):
        state = DelveState.new(PACK, 1, "fighter")
        self.assertEqual(state.room_id, "entry")
        self.assertEqual(state.enemies["captain"]["zone"], "doorway")
        self.assertEqual(state.enemies["captain"]["current_intent_id"], "smash")
        self.assertEqual(state.present_objects["entry"], ["bell", "chart", "dome"])
        self.assertEqual(state.present_objects["vault"], [])
        self.assertEqual(state.clocks["patrol"], 0)

    def test_instances_have_independent_mutable_values(self):
        a, b = DelveState.new(PACK, 1, "fighter"), DelveState.new(PACK, 1, "fighter")
        a.inventory.append("bell")
        a.flags.add("seen")
        a.present_objects["entry"].clear()
        a.bank_memory["key"] = ["variant"]
        a.event_log.append({"type": "test"})
        self.assertEqual(b.inventory, [])
        self.assertEqual(b.flags, set())
        self.assertEqual(b.present_objects["entry"], ["bell", "chart", "dome"])
        self.assertEqual(b.bank_memory, {})
        self.assertEqual(b.event_log, [])

    def test_hash_tracks_each_state_field(self):
        base = DelveState.new(PACK, 5, "fighter")
        mutations = [
            lambda s: setattr(s, "pack_id", "other_pack"),
            lambda s: setattr(s, "seed", 6),
            lambda s: setattr(s, "rng_draws", 1),
            lambda s: s.player.update(hp=s.player["hp"] - 1),
            lambda s: setattr(s, "room_id", "vault"),
            lambda s: s.inventory.append("bell"),
            lambda s: s.present_objects["entry"].pop(),
            lambda s: s.flags.add("changed"),
            lambda s: s.known_clues.append("bell_silenced"),
            lambda s: s.known_facts.append("captain_route"),
            lambda s: s.clocks.update(patrol=1),
            lambda s: s.enemies["captain"].update(hp=17),
            lambda s: setattr(s, "terminal", "quit"),
            lambda s: setattr(s, "turn", 1),
            lambda s: s.bank_memory.update(k=["v"]),
            lambda s: s.event_log.append({"type": "changed"}),
        ]
        original = base.snapshot()["canonical_state_hash"]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                changed = copy.deepcopy(base)
                mutate(changed)
                self.assertNotEqual(original, changed.snapshot()["canonical_state_hash"])


if __name__ == "__main__":
    unittest.main()
