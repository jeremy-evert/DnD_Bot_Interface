import copy
import json
import random
import re
import time
import unittest
from pathlib import Path

from delve.pack import load_pack
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
            "Rain taps the cracked stone. Bell [near]; chart [far]; dome [doorway].")
        state.room_id = "vault"
        state.player.update(hp=17, zone="doorway")
        state.clocks["patrol"] = 3
        state.present_objects["vault"] = ["ring"]
        self.assertEqual(render_status(state,self.pack),
            "HOLLOW VAULT [doorway]  HP 17/24  PATROL [###.]  Exits: W\n"
            "Hobgoblin Captain 18/18 HP [doorway] — The Captain winds up to SMASH the doorway — brace or shove!\n"
            "Hazard: COLLAPSE [hazard].  Objects: brass ring [near].")

    def test_help_death_victory_and_clock_bars(self):
        self.assertEqual(render_help(), "HELP — n/s/e/w move; x <thing> read; i inventory; a attack; sh <enemy> shove;\n"
            "b brace; t <item> throw; u <item> use; g <item> get; q quit.\n"
            "Enemy intent is shown before it resolves. Use zones, hazards, and exits.")
        event={"key":"terminal.death","fact_slots":{"cause":"the Captain's SMASH"}}
        death=render_death(event,self.pack)
        self.assertIn("YOU DIED — The Captain's SMASH broke through because of the Captain's SMASH.",death)
        self.assertIn("Retry hint: brace the declared smash, or shove him beneath the collapse.",death)
        self.assertIn("[r]etry or [q]uit",death)
        self.assertIn("VAULT CLEARED —",render_victory({"key":"terminal.victory","fact_slots":{}},self.pack))
        from delve.render import _bar
        self.assertEqual([_bar(i,4) for i in range(5)], ["....","#...","##..","###.","####"])

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
