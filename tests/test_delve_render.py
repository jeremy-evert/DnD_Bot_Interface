import copy
import json
import random
import re
import time
import unittest
from pathlib import Path
from io import StringIO
from unittest.mock import patch

from delve import __main__ as terminal
from delve.pack import load_pack
from delve.commands import HELP_FORMS
from delve.render import (RenderMemory, render_death, render_event, render_help,
                          render_status, render_victory, select_variant)
from delve.state import DelveState


SPEC = Path(__file__).parents[1] / "docs" / "DELVE_M1_SPEC.md"
SOURCE = SPEC.read_text(encoding="utf-8")
EXAMPLE = json.loads(re.search(r"### Complete valid example\s*```json\s*(.*?)\s*```", SOURCE, re.S).group(1))


class DelveRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = copy.deepcopy(EXAMPLE)
        replacements = [
            {"key":"room.enter","fact_slots":["room_name"],"variants":["Entering {{room_name}}."],"fallback":"Entering {{room_name}}."},
            {"key":"terminal.death","fact_slots":["cause"],"variants":["The Captain's SMASH broke through because of {{cause}}."],"fallback":"The Captain's SMASH broke through because of {{cause}}."},
            {"key":"terminal.retry","fact_slots":[],"variants":["brace the declared smash, or shove him beneath the collapse."],"fallback":"brace the declared smash, or shove him beneath the collapse."},
        ]
        entries = cls.data["bank"]["entries"]
        for replacement in replacements:
            old = next((i for i, entry in enumerate(entries) if entry["key"] == replacement["key"]), None)
            if old is None:
                entries.append(replacement)
            else:
                entries[old] = replacement
        cls.data["rooms"][0]["title"] = "Mossy Entry"
        for obj, name in zip(cls.data["rooms"][0]["objects"], ("Bell", "chart", "dome")):
            obj["name"] = name
        cls.data["rooms"][1]["objects"].append({"id":"ring","name":"brass ring","zone":"near","reader":{"on":"look","event_key":"object.read","effects":[]}})
        cls.pack = load_pack(cls.data)

    def test_determinism_seed_variance_and_no_repeat(self):
        entry = {"key":"test.line","fact_slots":["name"],"variants":["A {{name}}","B {{name}}","C {{name}}"],"fallback":"none"}
        self.assertEqual(select_variant(entry, 42, "test.line", {"name":"Ada"}, RenderMemory()),
                         select_variant(entry, 42, "test.line", {"name":"Ada"}, RenderMemory()))
        self.assertGreaterEqual(len({select_variant(entry, seed, "test.line", {"name":"Ada"}, RenderMemory()) for seed in range(20)}), 2)
        memory = RenderMemory()
        cycle = [select_variant(entry, 7, "test.line", {"name":"Ada"}, memory) for _ in range(4)]
        self.assertEqual(len(set(cycle[:3])), 3)
        self.assertEqual(cycle[3], cycle[0])
        select_variant(entry, 7, "test.line", {"name":"Bea"}, memory)
        self.assertEqual(len(memory.emitted), 2)
        before = dict(memory.emitted)
        select_variant(entry, 7, "test.line", {"name":"Ada"}, memory)
        self.assertEqual(len(memory.emitted["test.line|{" + '"name":"Bea"' + "}"]), len(before["test.line|{" + '"name":"Bea"' + "}"]))

    def test_fallback_missing_eligibility_unknown_key_and_unresolved(self):
        fallback_entry = {"key":"x","fact_slots":["expected"],"variants":[],"fallback":"fallback {{expected}}"}
        self.assertEqual(select_variant(fallback_entry, 1, "x", {"wrong":1}, RenderMemory()), "fallback {{expected}}")
        memory = RenderMemory()
        line = render_event({"key":"unknown.event","fact_slots":{}}, self.pack, 1, memory)
        self.assertIn("unknown event", line)
        broken = {"bank":{"entries":[{"key":"broken","fact_slots":[],"variants":["bad {{missing}}"],"fallback":"safe {{missing}}"}]}}
        line = render_event({"key":"broken","fact_slots":{}}, broken, 1, memory)
        self.assertEqual(line, "safe ")
        self.assertTrue(memory.problems)

    def test_extra_event_slots_do_not_force_death_fallback(self):
        data = copy.deepcopy(self.data)
        entry = next(e for e in data['bank']['entries'] if e['key'] == 'terminal.death')
        entry['fact_slots'] = ['cause']
        entry['variants'] = ['VARIANT: {{cause}}']
        entry['fallback'] = 'FALLBACK: {{cause}}'
        pack = load_pack(data)
        memory = RenderMemory()
        line = render_event({
            'key': 'terminal.death',
            'fact_slots': {'cause': 'the patrol', 'cause_enemy': '', 'cause_intent': ''},
        }, pack, 9, memory)
        self.assertEqual(line, 'VARIANT: the patrol')
        self.assertEqual(memory.problems, [])

    def test_missing_declared_slot_uses_fallback_and_records_problem(self):
        data = copy.deepcopy(self.data)
        entry = next(e for e in data['bank']['entries'] if e['key'] == 'terminal.death')
        entry['fact_slots'] = ['cause']
        entry['variants'] = ['VARIANT: {{cause}}']
        entry['fallback'] = 'FALLBACK: {{cause}}'
        pack = load_pack(data)
        memory = RenderMemory()
        line = render_event({'key': 'terminal.death', 'fact_slots': {}}, pack, 9, memory)
        self.assertEqual(line, 'FALLBACK: ')
        self.assertTrue(any('missing declared slots cause' in problem for problem in memory.problems))

    def test_event_replacement_is_deterministic(self):
        event = {"key":"object.read","fact_slots":{"object_name":"bell"}}
        a, b = RenderMemory(), RenderMemory()
        self.assertEqual(render_event(event,self.pack,9,a), render_event(event,self.pack,9,b))
        self.assertIn("bell", render_event(event,self.pack,9,RenderMemory()))

    def test_purity_and_no_global_random(self):
        state = DelveState.new(self.pack, 4, "fighter")
        before_state, before_pack = copy.deepcopy(state), copy.deepcopy(self.pack)
        random_before = random.getstate()
        render_status(state,self.pack)
        render_event({"key":"object.read","fact_slots":{"object_name":"bell"}},self.pack,4,RenderMemory())
        self.assertEqual(state,before_state)
        self.assertEqual(self.pack,before_pack)
        self.assertEqual(random.getstate(),random_before)

    def test_combat_status_fills_enemy_telegraph_slot_once(self):
        pack = load_pack(Path(__file__).parents[1] / "delve" / "content" / "mossy_fast_slice.json")
        state = DelveState.new(pack, 1, "fighter")
        state.room_id = "hollow_vault"
        state.player["zone"] = "doorway"
        memory = RenderMemory()
        screen = render_status(state, pack, memory)
        self.assertEqual(memory.problems, [])
        combat_line = screen.splitlines()[1]
        self.assertEqual(combat_line.count("Hobgoblin Captain"), 1)
        self.assertIn("Hobgoblin Captain", combat_line)

    def test_import_boundary_has_no_engine_or_network_dependencies(self):
        import ast
        source = Path(__file__).parents[1] / "delve" / "render.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        self.assertFalse(any(name.startswith(("delve.engine", "requests", "http", "urllib", "openai")) for name in imports))

    def test_exploration_and_combat_screens_exact(self):
        state = DelveState.new(self.pack, 4, "fighter")
        state.clocks["patrol"] = 2
        self.assertEqual(render_status(state,self.pack),
            "MOSSY ENTRY [near]  HP 24/24  PATROL [##..]  Exits: E\n"
            "Rain taps the cracked stone.\nObjects: Bell [near]; chart [far]; dome [doorway].")
        state.room_id = "vault"
        state.player.update(hp=17, zone="doorway")
        state.clocks["patrol"] = 3
        state.present_objects["vault"] = ["ring"]
        self.assertEqual(render_status(state,self.pack),
            "HOLLOW VAULT [doorway]  HP 17/24  PATROL [###.]  Exits: W\n"
            "Hobgoblin Captain 18/18 HP [doorway] — The Captain winds up to SMASH the doorway — brace or shove!\n"
            "Hazard: COLLAPSE [hazard].\nObjects: brass ring [near].")

    def test_help_death_victory_and_clock_bars(self):
        help_text = render_help(HELP_FORMS, "Brace heavy blows, shove swings and grabs, throw silver at a closed guard.")
        self.assertIn("HELP — n / north", help_text)
        self.assertIn("x/look", help_text)
        self.assertIn("b/brace", help_text)
        self.assertTrue(help_text.endswith("Brace heavy blows, shove swings and grabs, throw silver at a closed guard."))
        event={"key":"terminal.death","fact_slots":{"cause":"the Captain's SMASH"}}
        death=render_death(event,self.pack)
        self.assertIn("YOU DIED — The Captain's SMASH broke through because of the Captain's SMASH.",death)
        self.assertIn("Retry hint: brace the declared smash, or shove him beneath the collapse.",death)
        self.assertIn("[r]etry or [q]uit",death)
        victory = render_victory({"key":"terminal.victory","fact_slots":{}},self.pack)
        self.assertEqual(victory.count("\n"), 1)  # Amendment 4 item 6: only bank text and retry prompt.
        self.assertIn("VAULT CLEARED —",victory)
        from delve.render import _bar
        self.assertEqual([_bar(i,4) for i in range(5)], ["....","#...","##..","###.","####"])

    def test_status_telegraph_does_not_rotate_and_objects_are_labeled(self):
        data = copy.deepcopy(EXAMPLE)
        entry = next(e for e in data['bank']['entries'] if e['key'] == 'intent.captain.smash')
        entry['fact_slots'] = ['enemy_name']
        entry['variants'] = ['{{enemy_name}}: First.', '{{enemy_name}}: Second.']
        entry['fallback'] = '{{enemy_name}}: First.'
        pack = load_pack(data)
        state = DelveState.new(pack, 27, 'fighter')
        state.room_id = 'vault'; state.player['zone'] = 'doorway'
        memory = RenderMemory()
        first = render_status(state, pack, memory)
        second = render_status(state, pack, memory)
        self.assertEqual(first, second)  # Amendment 4 item 7: stable status wording.
        self.assertIn('Objects:', first)
        self.assertNotIn('brass ring [near]', first.splitlines()[1])

    def test_terminal_shows_one_stable_telegraph_per_turn(self):
        data = copy.deepcopy(EXAMPLE)
        entry = next(e for e in data['bank']['entries'] if e['key'] == 'intent.captain.smash')
        entry['fact_slots'] = ['enemy_name']
        entry['variants'] = ['{{enemy_name}}: First threat.', '{{enemy_name}}: Second threat.']
        entry['fallback'] = '{{enemy_name}}: First threat.'
        data['enemies'][0]['intent_cycle'] = ['smash']
        pack = load_pack(data)
        output = StringIO()
        with patch('delve.__main__.load_engine_ready_pack', return_value=pack), \
             patch('builtins.input', side_effect=['east', 'brace', 'q']), \
             patch('sys.stdout', output):
            self.assertEqual(terminal.main(['--seed', '37', '--class', 'fighter']), 0)
        transcript = output.getvalue()
        # Amendment 4 item 7: declaration events are not printed; status owns one stable line per turn.
        threat_lines = [line for line in transcript.splitlines() if 'threat.' in line]
        self.assertEqual(len(threat_lines), 2)
        self.assertEqual(threat_lines[0], threat_lines[1])

    def test_terminal_renders_parser_problems_from_the_bank(self):
        data = copy.deepcopy(EXAMPLE)
        data['rooms'][0]['objects'].extend([
            {'id':'brass_bell','name':'brass bell','zone':'near','reader':{'on':'look','event_key':'object.read','effects':[]}},
            {'id':'brass_bowl','name':'brass bowl','zone':'near','reader':{'on':'look','event_key':'object.read','effects':[]}},
        ])
        data['bank']['entries'].extend([
            {'key':'target.unknown','fact_slots':['target'],'variants':['Unknown {{target}}.'],'fallback':'Unknown {{target}}.'},
            {'key':'target.ambiguous','fact_slots':['target','candidates'],'variants':['{{target}}: {{candidates}}.'],'fallback':'{{target}}: {{candidates}}.'},
            {'key':'parse.unknown_verb','fact_slots':['verb'],'variants':['Verb {{verb}}?'],'fallback':'Verb {{verb}}?'},
        ])
        pack = load_pack(data)
        output = StringIO()
        with patch('delve.__main__.load_engine_ready_pack', return_value=pack), \
             patch('builtins.input', side_effect=['look nowhere', 'look brass', 'dance', 'q']), \
             patch('sys.stdout', output):
            self.assertEqual(terminal.main(['--seed', '2', '--class', 'fighter']), 0)
        transcript = output.getvalue()
        self.assertIn('Unknown nowhere.', transcript)
        self.assertIn('brass: brass bell, brass bowl.', transcript)
        self.assertIn('Verb dance?', transcript)

    def test_latency(self):
        state = DelveState.new(self.pack, 1, "fighter")
        event={"key":"object.read","fact_slots":{"object_name":"bell"}}
        samples=[]
        for _ in range(1000):
            memory=RenderMemory(); start=time.perf_counter_ns(); render_event(event,self.pack,1,memory); samples.append(time.perf_counter_ns()-start)
        p95=sorted(samples)[int(.95*len(samples))-1]/1_000_000
        self.assertLess(p95,5)
        samples=[]
        for _ in range(100):
            start=time.perf_counter_ns(); render_status(state,self.pack); samples.append(time.perf_counter_ns()-start)
        self.assertLess(sorted(samples)[94]/1_000_000,5)


if __name__ == "__main__":
    unittest.main()
