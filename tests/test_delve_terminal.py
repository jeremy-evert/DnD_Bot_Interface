import copy
import json
import random
import re
import socket
import time
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from delve import __main__ as terminal
from delve.commands import COMMANDS, HELP_FORMS, EnemyInspection, ParseProblem, parse_command
from delve.engine import Action, Engine
from delve.pack import load_engine_ready_pack, load_pack
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
        bank = {entry.key: entry for entry in self.pack.bank}
        for key in ('clue.mira', 'clue.dome', 'clue.chart'):
            self.assertTrue(any(line in output for line in bank[key].variants), key)

    def test_patrol_four_line_precedes_lower_hp_status(self):
        actions = [''] + ['attack'] * 6 + ['east', 'east', 'west', 'east', 'q']
        code, output = self.play(actions, seed=1, extra_args=('--class', 'fighter'))
        self.assertEqual(code, 0)
        entry = next(e for e in self.pack.bank if e.key == 'clock.threshold.patrol.4')
        line = next((v.replace('{{clock_label}}','PATROL').replace('{{at}}','4')
                     for v in entry.variants
                     if v.replace('{{clock_label}}','PATROL').replace('{{at}}','4') in output), None)
        self.assertIsNotNone(line)
        headers = [i for i, text in enumerate(output.splitlines()) if text.startswith('CHART CHAMBER [near]  HP')]
        self.assertTrue(headers)
        after_hit = output[output.index(line):]
        self.assertIn('CHART CHAMBER [near]  HP', after_hit)
        self.assertIn('HP 5/24', after_hit)

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
        self.assertEqual(ambiguous.message_key, "target.ambiguous")
        self.assertEqual(ambiguous.fact_slots["candidates"], "stone compass, star chart")
        self.assertIsInstance(unknown, ParseProblem)
        self.assertEqual((unknown.message_key, unknown.fact_slots), ("target.unknown", {"target": "moon rock"}))
        self.assertEqual(before, state.snapshot())

    def test_all_parser_aliases_are_listed_and_resolve_to_the_table_action(self):
        state = DelveState.new(self.pack, 1, "fighter")
        state.inventory.append("brass_ring")
        cases = {
            "n": ("n", "move"), "north": ("north", "move"),
            "s": ("s", "move"), "south": ("south", "move"),
            "e": ("e", "move"), "east": ("east", "move"),
            "w": ("w", "move"), "west": ("west", "move"),
            "go": ("go north", "move"),
            "x": ("x ring", "look"), "look": ("look ring", "look"),
            "examine": ("examine ring", "look"), "inspect": ("inspect ring", "look"),
            "read": ("read ring", "look"), "check": ("check ring", "look"),
            "study": ("study ring", "look"), "talk": ("talk ring", "look"),
            "speak": ("speak to ring", "look"), "ask": ("ask with ring", "look"),
            "greet": ("greet ring", "look"),
            "i": ("i", "inventory"), "inventory": ("inventory", "inventory"),
            "a": ("a goblin", "attack"), "attack": ("attack goblin", "attack"),
            "hit": ("hit goblin", "attack"), "strike": ("strike goblin", "attack"),
            "fight": ("fight goblin", "attack"), "swing": ("swing goblin", "attack"),
            "slash": ("slash goblin", "attack"), "heavy": ("heavy goblin", "attack"),
            "b": ("b", "brace"), "brace": ("brace", "brace"),
            "defend": ("defend", "brace"), "guard": ("guard", "brace"),
            "block": ("block", "brace"), "parry": ("parry", "brace"),
            "sh": ("sh goblin", "shove"), "shove": ("shove goblin", "shove"),
            "push": ("push goblin", "shove"), "shoulder": ("shoulder goblin", "shove"),
            "shunt": ("shunt goblin", "shove"),
            "t": ("t ring", "throw"), "throw": ("throw ring", "throw"),
            "toss": ("toss ring", "throw"), "hurl": ("hurl ring", "throw"),
            "fling": ("fling ring", "throw"),
            "u": ("u ring", "use"), "use": ("use ring", "use"),
            "give": ("give ring", "use"), "hand": ("hand ring", "use"),
            "show": ("show ring", "use"), "offer": ("offer ring", "use"),
            "present": ("present ring", "use"), "put": ("put ring", "use"),
            "drink": ("drink ring", "use"),
            "g": ("g ring", "get"), "get": ("get ring", "get"),
            "take": ("take ring", "get"), "grab": ("grab ring", "get"),
            "pick": ("pick ring", "get"), "pick up": ("pick up ring", "get"),
            "ret": ("ret west", "retreat"), "retreat": ("retreat west", "retreat"),
            "flee": ("flee west", "retreat"), "?": ("?", "help"),
            "help": ("help", "help"), "q": ("q", "quit"), "quit": ("quit", "quit"),
        }
        aliases = {alias for _, group, _ in COMMANDS for alias in group}
        self.assertEqual(aliases, set(cases))
        rendered_help = " ".join(HELP_FORMS).casefold()
        for alias, (line, expected_verb) in cases.items():
            with self.subTest(alias=alias):
                self.assertIn(alias, rendered_help)
                parsed = parse_command(line, state, self.pack)
                self.assertIsInstance(parsed, Action)
                self.assertEqual(parsed.verb, expected_verb)
        picked_up = parse_command("pick up ring", state, self.pack)
        self.assertEqual((picked_up.verb, picked_up.target_id), ("get", "brass_ring_obj"))

    def test_terminal_help_prints_every_parser_alias_then_a_bank_tip(self):
        _, output = self.play(["", "?", "q"], seed=1)
        help_output = output.split("HELP —", 1)[1]
        aliases = {alias for _, group, _ in COMMANDS for alias in group}
        for alias in aliases:
            with self.subTest(alias=alias):
                self.assertIn(alias, help_output.casefold())
        self.assertIn('marked (get)',help_output)
        bank_help = next(entry for entry in self.pack.bank if entry.key == "help")
        self.assertTrue(any(tip in output for tip in bank_help.variants))

    def test_natural_handover_target_forms_and_hazard_look(self):
        state = DelveState.new(self.pack, 1, "fighter")
        state.room_id = "mira_gallery"
        state.inventory.append("brass_ring")
        for line in ("give ring to Mira", "give Mira brass ring", "use ring on nameplate",
                     "put brass ring in nameplate", "show ring"):
            with self.subTest(line=line):
                parsed = parse_command(line, state, self.pack)
                self.assertIsInstance(parsed, Action)
                self.assertEqual((parsed.verb, parsed.target_id), ("use", "brass_ring"))
        invalid_target = parse_command("give ring to moon", state, self.pack)
        self.assertIsInstance(invalid_target, ParseProblem)
        self.assertEqual(invalid_target.message_key, "target.unknown")

        state.room_id = "hollow_vault"
        state.flags.add("captain_route_known")
        before = copy.deepcopy(state.snapshot())
        for target in ("collapse", "ceiling", "hazard", "arch"):
            with self.subTest(hazard=target):
                problem = parse_command(f"x {target}", state, self.pack)
                self.assertIsInstance(problem, ParseProblem)
                self.assertIn("shove can put", problem.text.casefold())
                self.assertEqual(before, state.snapshot())

    def test_enemy_look_resolves_without_turn_or_state_change(self):
        state=DelveState.new(self.pack,1,'fighter')
        before=copy.deepcopy(state.snapshot())
        for command in ('x Goblin','look Goblin','x goblin','x gob'):
            parsed=parse_command(command,state,self.pack)
            self.assertEqual(getattr(parsed,'enemy_id',None),'goblin')
        state.room_id='hollow_vault'
        for command in ('x captain','look Hobgoblin Captain','x Captain'):
            parsed=parse_command(command,state,self.pack)
            self.assertEqual(getattr(parsed,'enemy_id',None),'captain')
        state.room_id='mossy_entry'
        real_apply=Engine.apply
        applied=[]
        def record_apply(engine, action):
            applied.append(action)
            return real_apply(engine, action)
        with patch('builtins.input',side_effect=['x Goblin','q']), patch('sys.stdout',StringIO()) as output:
            with patch.object(terminal.Engine,'apply',record_apply):
                self.assertEqual(terminal.main(['--seed','1','--class','fighter']),0)
        self.assertEqual([action.verb for action in applied],['quit'])
        text=output.getvalue()
        self.assertIn('Goblin',text)
        self.assertIn('8/8 HP',text)
        self.assertIn('[doorway]',text)
        self.assertIn('grab',text.casefold())
        self.assertEqual(before,state.snapshot())

    def test_present_takeable_object_not_in_hand_gets_pickup_hint(self):
        state=DelveState.new(self.pack,1,'fighter')
        state.room_id='collapsed_observatory'
        for command in ('use offering bowl','throw offering bowl','give offering bowl'):
            with self.subTest(command=command):
                problem=parse_command(command,state,self.pack)
                self.assertIsInstance(problem,ParseProblem)
                self.assertEqual(problem.message_key,'target.not_held')
                self.assertEqual(problem.fact_slots,{'target':'offering bowl'})
        # Parser response is bank-rendered and leaves the room loop untouched.
        _,output=self.play(['']+['attack']*6+['east','use offering bowl','q'],seed=1)
        self.assertIn('get offering bowl',output)

    def test_not_held_bank_variants_follow_the_short_dry_voice(self):
        entry=next(e for e in self.pack.bank if e.key=='target.not_held')
        self.assertGreaterEqual(len(set(entry.variants)),4)
        self.assertTrue(all('{{target}}' in line for line in entry.variants))
        self.assertTrue(all(not re.search(r'\d', line) for line in entry.variants))

    def test_fire_hazard_inspection_does_not_claim_shove_triggers_it(self):
        data=copy.deepcopy(json.loads(re.search(r'### Complete valid example\s*```json\s*(.*?)\s*```',
                                                (Path(__file__).parents[1]/'docs/DELVE_M1_SPEC.md').read_text(),re.S).group(1)))
        data['hazards'][0].update(tag='fire',trigger={'action':'move','requires_flag_id':None},
                                  effects=[{'type':'damage','target':'player','amount':3}])
        pack=load_pack(data); state=DelveState.new(pack,1,'fighter'); state.room_id='vault'
        parsed=parse_command('x fire',state,pack)
        self.assertIsInstance(parsed,ParseProblem)
        self.assertIn('burns when you enter',parsed.text)
        self.assertNotIn('shove',parsed.text)

    def test_throw_at_keeps_named_enemy_target(self):
        state=DelveState.new(self.pack,1,'fighter')
        state.room_id='hollow_vault'
        state.inventory.append('brass_ring')
        parsed=parse_command('throw brass ring at Hobgoblin Captain',state,self.pack)
        self.assertEqual((parsed.verb,parsed.target_id,parsed.enemy_target_id),('throw','brass_ring','captain'))

    def test_hand_over_ring_consumes_it_but_mira_clue_still_works(self):
        actions=['']+['attack']*6+['get brass ring','east','south','give ring to Mira','inventory',
                         'give ring to Mira','inventory','x Mira','q']
        code,output=self.play(actions,seed=1)
        self.assertEqual(code,0)
        self.assertIn('In hand and in pocket: .',output)
        self.assertIn('Not here. Some things only work in the right company.',output)
        self.assertTrue(any(line in output for line in {e.key:e for e in self.pack.bank}['clue.mira'].variants))

    def test_unknown_verb_bank_line_always_points_to_help(self):
        parsed = parse_command("teleport", DelveState.new(self.pack, 1, "fighter"), self.pack)
        self.assertIsInstance(parsed, ParseProblem)
        self.assertEqual(parsed.message_key, "parse.unknown_verb")
        line = render_event({"key": parsed.message_key, "fact_slots": parsed.fact_slots},
                            self.pack, 1, RenderMemory())
        self.assertTrue(line.endswith("Type ? for the list."), line)

    def test_alias_line_fuzz_never_crashes_or_mutates_on_parse_problem(self):
        state = DelveState.new(self.pack, 5, "fighter")
        aliases = sorted({alias for _, group, _ in COMMANDS for alias in group})
        suffixes = ("", " goblin", " ring", " to Mira", " on nameplate", " moon rock", " north")
        rng = random.Random(612)
        for _ in range(400):
            line = rng.choice(aliases) + rng.choice(suffixes)
            before = copy.deepcopy(state.snapshot())
            parsed = parse_command(line, state, self.pack)
            self.assertTrue(isinstance(parsed, (Action, ParseProblem, EnemyInspection)), line)
            if isinstance(parsed, ParseProblem):
                self.assertEqual(before, state.snapshot(), line)

    def test_handover_input_replays_through_terminal_and_reveals_mira_clue(self):
        actions = [""] + ["hit goblin"] * 6 + ["get ring", "east", "south",
                                                     "give ring to Mira", "give Mira brass ring",
                                                     "use ring on nameplate",
                                                     "put brass ring in nameplate", "talk Mira", "x Mira", "q"]
        code, output = self.play(actions, seed=1)
        self.assertEqual(code, 0)
        self.assertIn("Give her the brass ring", output)
        bank = {entry.key: entry for entry in self.pack.bank}
        self.assertTrue(any(line in output for line in bank["clue.mira"].variants))

    def test_hazard_alias_message_reaches_terminal_without_engine_action(self):
        actions = [""] + ["hit goblin"] * 6 + ["east", "east", "north", "x collapse", "q"]
        code, output = self.play(actions, seed=1)
        self.assertEqual(code, 0)
        self.assertIn("stone above looks loose", output.casefold())
        self.assertNotIn("shove can put", output.casefold())
        self.assertIn("HOLLOW VAULT", output)

    def test_collapse_hint_changes_after_route_fact_is_known(self):
        state = DelveState.new(self.pack, 1, "fighter")
        state.room_id = "hollow_vault"
        unknown = parse_command("x collapse", state, self.pack)
        self.assertIn("nothing tells you where he stands", unknown.text.casefold())
        state.flags.add("captain_route_known")
        known = parse_command("x collapse", state, self.pack)
        self.assertIn("shove can put", known.text.casefold())

    def test_input_unicode_errors_and_surrogates_do_not_crash_or_echo(self):
        from io import StringIO
        cases = [UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid start byte'), '\ud800']
        for bad in cases:
            with self.subTest(bad=repr(bad)), patch('builtins.input', side_effect=[bad, 'q']), patch('sys.stdout', StringIO()) as output:
                self.assertEqual(terminal.main(['--seed','1','--class','fighter']), 0)
                rendered=output.getvalue()
                self.assertIn("[undecodable input]", rendered)
                self.assertNotIn('\\ud800', rendered)

    def test_drink_rainwater_uses_held_offering_bowl(self):
        actions = [""] + ["hit goblin"] * 6 + ["east", "get offering bowl", "drink rainwater", "q"]
        code, output = self.play(actions, seed=1)
        self.assertEqual(code, 0)
        self.assertIn("stand straighter", output)
        self.assertIn("COLLAPSED OBSERVATORY [near]  HP 17/24", output)

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
