import copy
import random
import socket
import time
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from delve import __main__ as terminal
from delve.commands import ParseProblem, parse_command
from delve.engine import Action, Engine
from delve.pack import load_engine_ready_pack
from delve.render import RenderMemory, render_event, render_status
from delve.state import DelveState


PACK_PATH = Path(__file__).parents[1] / "delve" / "content" / "mossy_fast_slice.json"


class DelveTerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = load_engine_ready_pack(PACK_PATH)

    def play(self, actions, seed=0, extra_args=()):
        output = StringIO()
        with patch("builtins.input", side_effect=actions), patch("sys.stdout", output):
            code = terminal.main(["--seed", str(seed), *extra_args])
        return code, output.getvalue()

    def winning_script(self):
        return [""] + ["attack"] * 6 + [
            "get brass ring", "east", "south", "use brass ring", "look mira", "north",
            "look collapsed dome", "east", "look star chart", "north",
            "attack", "brace", "attack", "shove", "attack", "q",
        ]

    def test_scripted_shipped_pack_win(self):
        code, output = self.play(self.winning_script(), seed=1)
        self.assertEqual(code, 0)
        self.assertIn("VAULT CLEARED", output)
        self.assertIn("Mira folds her arms", output)
        self.assertIn("You find the tell in collapsed dome", output)
        self.assertIn("marked star sits directly above", output)
        self.assertIn("You know it now", output)

    def test_conventional_forms_parse_without_followup_direction_prompt(self):
        state = DelveState.new(self.pack, 1, "fighter")
        forms = {"n": ("move", "north"), "s": ("move", "south"), "e": ("move", "east"),
                 "w": ("move", "west"), "north": ("move", "north"), "south": ("move", "south"),
                 "east": ("move", "east"), "west": ("move", "west"),
                 "go north": ("move", "north"), "go south": ("move", "south"),
                 "go east": ("move", "east"), "go west": ("move", "west"),
                 "x": ("look", None), "look": ("look", None), "x brass ring": ("look", "brass_ring_obj"),
                 "look ring": ("look", "brass_ring_obj"), "i": ("inventory", None),
                 "inventory": ("inventory", None), "get brass_ring_obj": ("get", "brass_ring_obj"),
                 "get brass ring": ("get", "brass_ring_obj"), "get ring": ("get", "brass_ring_obj"),
                 "g ring": ("get", "brass_ring_obj"), "take ring": ("get", "brass_ring_obj"),
                 "a": ("attack", None), "attack goblin": ("attack", "goblin"),
                 "sh": ("shove", None), "shove goblin": ("shove", "goblin"),
                 "b": ("brace", None), "brace": ("brace", None), "t brass ring": ("throw", "brass_ring"),
                 "throw brass ring at goblin": ("throw", "brass_ring"),
                 "t brass ring at goblin": ("throw", "brass_ring"),
                 "u brass ring": ("use", "brass_ring"), "use brass ring": ("use", "brass_ring"),
                 "retreat west": ("retreat", "west"), "flee west": ("retreat", "west"),
                 "ret west": ("retreat", "west"), "?": ("help", None), "help": ("help", None),
                 "q": ("quit", None), "quit": ("quit", None)}
        state.inventory.append("brass_ring")
        for line, expected in forms.items():
            with self.subTest(line=line):
                parsed = parse_command(line, state, self.pack)
                self.assertIsInstance(parsed, Action)
            self.assertEqual((parsed.verb, parsed.direction or parsed.target_id), expected)
        calls = iter(["n", "s", "e", "w"])
        with patch("builtins.input", side_effect=lambda prompt="": next(calls)) as mocked:
            for _ in range(4): input("> ")
        self.assertEqual(mocked.call_count, 4)
        with patch("builtins.input", side_effect=["", "n", "s", "e", "w", "q"]) as mocked, \
             patch("sys.stdout", StringIO()):
            terminal.main(["--seed", "1"])
        self.assertEqual(mocked.call_count, 6)  # one class line and one line per command

    def test_ambiguous_and_unknown_are_read_only_and_helpful(self):
        state = DelveState.new(self.pack, 1, "fighter")
        # "s" matches both the stone compass and star chart in the chart chamber.
        state.room_id = "chart_chamber"
        before = copy.deepcopy(state.snapshot())
        ambiguous = parse_command("look s", state, self.pack)
        unknown = parse_command("get moon rock", state, self.pack)
        self.assertIsInstance(ambiguous, ParseProblem)
        self.assertIn("Ambiguous", ambiguous.text)
        self.assertIsInstance(unknown, ParseProblem)
        self.assertIn("No object", unknown.text)
        self.assertEqual(before, state.snapshot())
        _, output = self.play(["", "attack", "east", "east", "look s", "get moon rock", "q"])
        self.assertIn("Ambiguous target", output)
        self.assertIn("No object matches", output)

    def test_death_retry_increments_seed_and_quit_returns_zero(self):
        calls = ["attack", "east", "east", "north", "brace", "attack", "brace", "attack", "brace", "r", "q"]
        code, output = self.play(calls, seed=6, extra_args=("--class", "fighter"))
        self.assertEqual(code, 0)
        self.assertIn("YOU DIED", output)
        self.assertRegex(output, r"YOU DIED — .*Goblin strike")
        self.assertIn("Retry hint:", output)
        self.assertIn("[r]etry or [q]uit", output)
        self.assertIn("seed 7", output)

    def test_eof_and_keyboard_interrupt_exit_cleanly(self):
        with patch("builtins.input", side_effect=["", EOFError]), patch("sys.stdout", StringIO()):
            self.assertEqual(terminal.main(["--seed", "1"]), 0)
        with patch("builtins.input", side_effect=KeyboardInterrupt), patch("sys.stdout", StringIO()):
            self.assertEqual(terminal.main(["--seed", "1"]), 0)

    def test_random_lines_never_raise_and_parse_problems_do_not_mutate(self):
        state = DelveState.new(self.pack, 11, "fighter")
        rng = random.Random(44)
        alphabet = "abcdefghijklmnopqrstuvwxyz <>!?"
        for _ in range(300):
            line = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 50)))
            before = copy.deepcopy(state.snapshot())
            parsed = parse_command(line, state, self.pack)
            if isinstance(parsed, ParseProblem):
                self.assertEqual(before, state.snapshot())
        lines = ["" ] + ["".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 50)))
                          for _ in range(300)] + ["q"]
        with patch("builtins.input", side_effect=lines), patch("sys.stdout", StringIO()):
            self.assertEqual(terminal.main(["--seed", "11"]), 0)

    def test_timing_determinism_and_no_network(self):
        inputs = [""] + ["?"] * 100 + ["q"]
        output = StringIO()
        with patch("builtins.input", side_effect=inputs), patch("sys.stdout", output), patch.object(socket, "socket", side_effect=AssertionError("network used")):
            self.assertEqual(terminal.main(["--seed", "123"]), 0)
        first = output.getvalue()
        output2 = StringIO()
        with patch("builtins.input", side_effect=inputs), patch("sys.stdout", output2), patch.object(socket, "socket", side_effect=AssertionError("network used")):
            self.assertEqual(terminal.main(["--seed", "123"]), 0)
        self.assertEqual(first, output2.getvalue())

        samples = []
        starts = []
        real_parse = terminal.parse_command
        real_render = terminal.render_event
        def timed_parse(*args):
            starts.append(time.perf_counter_ns())
            return real_parse(*args)
        def timed_render(*args):
            rendered = real_render(*args)
            samples.append(time.perf_counter_ns() - starts.pop(0))
            return rendered
        with patch("builtins.input", side_effect=[""] + ["?"] * 100 + ["q"]), \
             patch("sys.stdout", StringIO()), patch.object(terminal, "parse_command", timed_parse), \
             patch.object(terminal, "render_event", timed_render), \
             patch.object(socket, "socket", side_effect=AssertionError("network used")):
            self.assertEqual(terminal.main(["--seed", "123"]), 0)
        self.assertLess(sorted(samples)[94] / 1_000_000, 100)

    def test_terminal_only_constructs_actions_and_engine_apply_mutates(self):
        state = DelveState.new(self.pack, 1, "fighter")
        before = copy.deepcopy(state.snapshot())
        parsed = parse_command("?", state, self.pack)
        self.assertEqual(before, state.snapshot())
        self.assertIsInstance(parsed, Action)
        Engine(self.pack, state).apply(parsed)
        self.assertEqual(state.turn, 1)

        instances = []
        expected_snapshots = []
        real_parser = terminal.parse_command
        def capture_before_parse(line, state, pack):
            expected_snapshots.append(copy.deepcopy(state.snapshot()))
            return real_parser(line, state, pack)
        class SpyEngine(Engine):
            def __init__(self, pack, state):
                super().__init__(pack, state)
                instances.append(self)
            def apply(self, action):
                self_outer.assertEqual(self.state.snapshot(), expected_snapshots.pop(0))
                return super().apply(action)
        self_outer = self
        with patch("delve.__main__.Engine", SpyEngine), \
             patch("delve.__main__.parse_command", capture_before_parse), \
             patch("builtins.input", side_effect=["", "?", "q"]), patch("sys.stdout", StringIO()):
            self.assertEqual(terminal.main(["--seed", "1"]), 0)
        self.assertTrue(instances)


if __name__ == "__main__":
    unittest.main()
