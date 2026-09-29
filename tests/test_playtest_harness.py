import random
import unittest
from unittest.mock import patch

from playtest.harness import replay, snapshot


class PlaytestHarnessTests(unittest.TestCase):
    @staticmethod
    def setup_calls(*actions):
        return ["Ada", "fighter", *actions]

    def test_same_seed_and_inputs_have_identical_output_and_snapshot(self):
        calls = self.setup_calls("attack", "attack", "status")
        first, second = replay(41, calls), replay(41, calls)
        self.assertEqual(first.output, second.output)
        self.assertEqual(snapshot(first.witness), snapshot(second.witness))
        self.assertEqual(snapshot(first.witness)["canonical_state_hash"],
                         snapshot(second.witness)["canonical_state_hash"])

    def test_seed_changes_combat_output_but_each_seed_is_repeatable(self):
        calls = self.setup_calls(*(["attack"] * 8))
        outputs = {}
        for seed in range(8):
            one, two = replay(seed, calls), replay(seed, calls)
            self.assertEqual(one.output, two.output)
            self.assertEqual(snapshot(one.witness), snapshot(two.witness))
            outputs[seed] = one.output
        self.assertGreater(len(set(outputs.values())), 1)

    def test_exhaustion_is_reported_separately_from_exceptions(self):
        exhausted = replay(1, ["Ada"])
        self.assertTrue(exhausted.exhausted)
        self.assertIsNone(exhausted.error)
        self.assertEqual(exhausted.consumed, 1)

        class RaisingRecorder:
            def __init__(self):
                pass

            def record(self, event, **fields):
                raise RuntimeError("recorder exploded")

        with patch("playtest.harness.MemoryRecorder", RaisingRecorder):
            failed = replay(1, ["Ada", "fighter"])
        self.assertFalse(failed.exhausted)
        self.assertEqual(failed.error, "RuntimeError('recorder exploded')")

    def test_replay_does_not_change_global_random_state(self):
        before = random.getstate()
        replay(77, self.setup_calls("attack", "look"))
        self.assertEqual(random.getstate(), before)

    def test_two_input_move_reaches_mossy_delves_neighbor(self):
        result = replay(0, self.setup_calls(*(["attack"] * 20), "move", "east"))
        self.assertIsNone(result.error)
        self.assertEqual(result.witness.current_room_id, "stores")
        self.assertEqual(result.witness.room.name, "Forgotten Stores")

    def test_output_does_not_depend_on_global_random_seed(self):
        calls = self.setup_calls(*(["attack"] * 7))
        random.seed(1234)
        first = replay(29, calls).output
        random.seed(5678)
        second = replay(29, calls).output
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
