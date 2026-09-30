import copy
import json
import random
import re
import unittest
from pathlib import Path

from delve.engine import Action, Engine
from delve.pack import _effect, load_pack
from delve.state import DelveState

SPEC = Path(__file__).parents[1] / 'docs' / 'DELVE_M1_SPEC.md'
EXAMPLE = json.loads(re.search(r'### Complete valid example\s*```json\s*(.*?)\s*```', SPEC.read_text(), re.S).group(1))


class ScriptedRandom(random.Random):
    def randint(self, a, b):
        return 20 if b == 20 else 2


def make_pack():
    d = copy.deepcopy(EXAMPLE)
    # Amendment 3 point 5/6 event contract; use a single bank entry per engine event.
    keys = {x['key'] for x in d['bank']['entries']}
    for key in ('shove.success', 'shove.fail', 'throw.interrupt', 'throw.fizzle', 'intent.cancelled', 'hazard.trigger', 'enemy.hit', 'enemy.miss', 'attack.hit', 'attack.miss', 'brace.success', 'brace.wasted', 'combat.not_yet'):
        if key not in keys:
            d['bank']['entries'].append({'key': key, 'fact_slots': [], 'variants': [key], 'fallback': key})
    if 'hazard' not in d['rooms'][1]['zones']: d['rooms'][1]['zones'].append('hazard')
    d['enemies'][0]['intent_cycle'] = ['strike', 'rush', 'smash', 'grab', 'guard']
    d['enemies'][0]['intents'] = [
        {'id': t, 'type': t, 'telegraph_key': 'intent.captain.smash', 'target_zone': 'doorway',
         'effects': [{'type': 'damage', 'target': 'player', 'amount': 0}], 'counters': []}
        for t in ('strike', 'rush', 'smash', 'grab', 'guard')]
    d['hazards'] = [{'id': 'vault_collapse', 'room_id': 'vault', 'zone': 'hazard', 'tag': 'collapse',
                     'event_key': 'hazard.collapse', 'trigger': {'action': 'shove', 'requires_flag_id': 'captain_route_known'},
                     'effects': [{'type': 'damage', 'target': 'enemy', 'amount': 6}]}]
    d['items'] = [
        {'id': 'clay_cup', 'name': 'clay cup', 'reader': {'on': 'throw', 'event_key': 'throw.cup', 'effects': []}, 'throw_tags': ['interrupt_grab']},
        {'id': 'silver_leaf', 'name': 'silver leaf', 'reader': {'on': 'throw', 'event_key': 'throw.leaf', 'effects': []}, 'throw_tags': ['interrupt_guard']},
    ]
    for key in ('throw.cup', 'throw.leaf'):
        d['bank']['entries'].append({'key':key,'fact_slots':['item_name'],'variants':['{{item_name}}'],'fallback':'{{item_name}}'})
    return load_pack(d)


def assert_telegraph(testcase, log):
    declared = {}
    for event in log:
        key = event['key']
        if key.startswith('intent.'):
            declared[event['fact_slots'].get('enemy_name')] = True
        elif key == 'enemy.hit':
            name = event['fact_slots'].get('enemy_name')
            testcase.assertTrue(declared.get(name), f'{name} hit without a current telegraph')
            declared[name] = False


class HazardTests(unittest.TestCase):
    def setUp(self):
        self.pack = make_pack()
        self.s = DelveState.new(self.pack, 21, 'fighter')
        self.s.room_id = 'vault'; self.s.player['zone'] = 'doorway'
        self.e = Engine(self.pack, self.s)
        self.s.rng = ScriptedRandom(0)
        self.s.event_log.append(self.e._event('intent.captain.smash', {'enemy_name': 'Hobgoblin Captain'}, typ='enemy_intent').to_dict())

    def act(self, verb, target=None): return self.e.apply(Action(verb, target))

    def test_shove_intent_table_and_captain_payoff_gate(self):
        foe = self.s.enemies['captain']
        for kind in ('strike', 'rush', 'grab'):
            foe['current_intent_id'] = kind; foe['zone'] = 'doorway'; before = self.s.rng_draws
            events = self.act('shove', 'captain')
            self.assertEqual(foe['zone'], 'far'); self.assertEqual(self.s.rng_draws-before, 0)
            self.assertIn('shove.success', [e.key for e in events])
        foe['current_intent_id'] = 'smash'; foe['zone'] = 'doorway'; foe['hp'] = 18
        before = self.s.rng_draws
        events = self.act('shove', 'captain')
        self.assertEqual(self.s.rng_draws-before, 2); self.assertEqual(foe['zone'], 'doorway')
        self.assertIn('shove.fail', [e.key for e in events]); self.assertIn('enemy.hit', [e.key for e in events])
        self.s.flags.add('captain_route_known'); foe['hp'] = 18; foe['zone'] = 'doorway'; foe['current_intent_id'] = 'smash'
        before = self.s.rng_draws
        events = self.act('shove', 'captain')
        self.assertEqual(self.s.rng_draws-before, 0); self.assertEqual(foe['zone'], 'hazard'); self.assertEqual(foe['hp'], 12)
        self.assertEqual([e.key for e in events if e.key in ('hazard.collapse','shove.success')], ['hazard.collapse','shove.success'])

    def test_guard_shove_persists_and_unstable_ground_affects_actor(self):
        foe = self.s.enemies['captain']; foe['current_intent_id'] = 'guard'
        events = self.act('shove', 'captain')
        self.assertEqual([e.key for e in events], ['shove.fail']); self.assertEqual(foe['current_intent_id'], 'guard'); self.assertEqual(self.s.rng_draws, 0)
        d = copy.deepcopy(EXAMPLE); d['hazards'] = [{'id':'unstable_ground','room_id':'vault','zone':'hazard','tag':'unstable_ground','event_key':'hazard.collapse','trigger':{'action':'shove','requires_flag_id':'route_flag'},'effects':[{'type':'damage','target':'player','amount':2}]}]
        d['rooms'][0]['objects'][0]['reader']['effects'].append({'type':'set_flag','flag_id':'route_flag','value':True})
        d['bank']['entries'].append({'key':'shove.fail','fact_slots':[],'variants':['fail'],'fallback':'fail'})
        guard = copy.deepcopy(d['enemies'][0]['intents'][0]); guard.update({'id':'guard','type':'guard'}); d['enemies'][0]['intents'].append(guard); d['enemies'][0]['intent_cycle']=['guard']
        pack = load_pack(d); s = DelveState.new(pack, 1, 'fighter'); s.room_id='vault'; s.player['zone']='doorway'; e=Engine(pack,s)
        s.event_log.append(e._event('intent.captain.smash', {'enemy_name':'Hobgoblin Captain'}).to_dict())
        e.apply(Action('shove','captain'))
        self.assertEqual(s.player['zone'], 'hazard'); self.assertEqual(s.player['hp'], 22)

    def test_throw_matching_mismatch_and_invalid(self):
        self.s.inventory.append('clay_cup'); self.s.enemies['captain']['current_intent_id'] = 'grab'
        before = self.s.rng_draws; events = self.act('throw', 'clay_cup')
        self.assertEqual(self.s.rng_draws-before, 0); self.assertNotIn('clay_cup', self.s.inventory)
        self.assertEqual([e.key for e in events if e.key.startswith('throw.') or e.key == 'intent.cancelled'],
                         ['throw.cup', 'intent.cancelled'])  # Amendment 4 item 2: reader owns the single throw line.
        self.assertEqual(events[0].fact_slots, {'item_name': 'clay cup'})
        self.s.inventory.append('silver_leaf'); self.s.enemies['captain']['current_intent_id'] = 'guard'
        before = self.s.rng_draws; events = self.act('throw', 'silver_leaf')
        self.assertEqual(self.s.rng_draws-before, 0); self.assertNotIn('silver_leaf', self.s.inventory)
        self.assertNotIn('enemy.hit', [e.key for e in events])
        self.s.inventory.append('clay_cup'); self.s.enemies['captain']['current_intent_id'] = 'strike'
        before = self.s.rng_draws; events = self.act('throw', 'clay_cup')
        self.assertEqual(self.s.rng_draws-before, 2); self.assertIn('throw.fizzle', [e.key for e in events]); self.assertEqual(events[0].fact_slots, {'item_name':'clay cup'}); self.assertNotIn('clay_cup', self.s.inventory)
        before = self.s.rng_draws; inv = list(self.s.inventory); events = self.act('throw', 'missing')
        self.assertEqual(self.s.rng_draws, before); self.assertEqual(self.s.inventory, inv); self.assertEqual(events[0].key, 'target.unknown')
        # An unheld item and a room without a living enemy are explanatory no-ops.
        self.s.enemies['captain']['hp'] = 0; self.s.inventory.append('clay_cup')
        snap = self.s.snapshot(); events = self.act('throw', 'clay_cup')
        self.assertEqual(events[0].key, 'target.unknown')  # Amendment 4 item 8 retires combat.not_yet.
        self.assertEqual(self.s.snapshot()['rng_draws'], snap['rng_draws'])
        self.assertIn('clay_cup', self.s.inventory)

    def test_hazard_tag_matrix_and_cover(self):
        # Each tag is tested with a pack deep-copied from the complete valid example.
        cases = {
            'collapse': ([{'type':'damage','target':'enemy','amount':3}], ('hp', 15)),
            'fire': ([{'type':'damage','target':'enemy','amount':4}], ('hp', 14)),
            'drop': ([], ('zone', 'hazard')),
            'noise': ([{'type':'tick_clock','clock_id':'patrol','amount':1}], ('clock', 1)),
        }
        for tag, (effects, expected) in cases.items():
            with self.subTest(tag=tag):
                d=copy.deepcopy(EXAMPLE); d['hazards']=[{'id':'tag_hazard','room_id':'vault','zone':'hazard','tag':tag,'event_key':'hazard.collapse','trigger':{'action':'shove','requires_flag_id':None},'effects':effects}]
                if tag == 'fire':
                    # Fire is an entry hazard, while other shove hazards use the shove seam.
                    d['hazards'][0]['trigger']={'action':'move','requires_flag_id':None}
                    d['hazards'][0]['effects']=[{'type':'damage','target':'player','amount':3}]
                    pack=load_pack(d); s=DelveState.new(pack,7,'fighter'); e=Engine(pack,s)
                    s.room_id='entry'; e.apply(Action('move',direction='east'))
                    expected=('player_hp', 21)
                else:
                    pack=load_pack(d); s=DelveState.new(pack,7,'fighter'); s.room_id='vault'; s.player['zone']='doorway'; e=Engine(pack,s)
                    if tag == 'collapse': s.enemies['captain']['current_intent_id']='smash'
                    e._shove(e._living_enemy(), e._current_intent(e._living_enemy()), [])
                    expected=expected
                key,value=expected
                actual=(s.player['hp'] if key=='player_hp' else s.enemies['captain']['hp'] if key=='hp'
                        else s.enemies['captain']['zone'] if key=='zone' else s.clocks['patrol'])
                self.assertEqual(actual,value)
        # Cover improves a brace outcome by one extra point, with a zero floor.
        d=copy.deepcopy(EXAMPLE); d['hazards']=[{'id':'cover_hazard','room_id':'vault','zone':'hazard','tag':'cover','event_key':'hazard.collapse','trigger':{'action':'shove','requires_flag_id':None},'effects':[]}]
        pack=load_pack(d); s=DelveState.new(pack,7,'fighter'); s.room_id='vault'; s.player['zone']='doorway'; s.rng=ScriptedRandom(0); e=Engine(pack,s); foe=e._living_enemy()
        e._resolve_intent(foe, 'halve', [])
        self.assertEqual(s.player['hp'], 23)

    def test_open_exit_and_enemy_move_zone_effects_are_observable(self):
        d=copy.deepcopy(EXAMPLE)
        d['rooms'][0]['exits'][0]['gate']={'kind':'flag','flag_id':'door_open','denial_event_key':'gate.closed'}
        d['bank']['entries'].append({'key':'gate.closed','fact_slots':[],'variants':['Closed.'],'fallback':'Closed.'})
        d['rooms'][0]['objects'][0]['reader']['effects'].append({'type':'open_exit','room_id':'entry','direction':'east'})
        pack=load_pack(d); s=DelveState.new(pack,1,'fighter'); e=Engine(pack,s)
        e.apply(Action('look','bell'))
        self.assertEqual(e.apply(Action('move',direction='east'))[0].key,'room.enter')

        d=copy.deepcopy(EXAMPLE)
        d['enemies'][0]['intents'][0]['effects']=[{'type':'move_zone','actor':'enemy','zone':'far'}]
        pack=load_pack(d); s=DelveState.new(pack,1,'fighter'); s.room_id='vault'; e=Engine(pack,s)
        foe=e._living_enemy(); s.enemies[foe.id]['current_intent_id']=foe.intent_cycle[0]
        e._resolve_intent(foe,events=[])
        self.assertEqual(s.enemies[foe.id]['zone'],'far')

    def test_each_effect_type_changes_state_or_emits_an_event(self):
        cases=(
            ('damage', {'type':'damage','target':'player','amount':2}, 'hp'),
            ('heal', {'type':'heal','target':'player','amount':2}, 'hp'),
            ('tick_clock', {'type':'tick_clock','clock_id':'patrol','amount':1}, 'clock'),
            ('move_zone_player', {'type':'move_zone','actor':'player','zone':'far'}, 'player_zone'),
            ('move_zone_enemy', {'type':'move_zone','actor':'enemy','zone':'far'}, 'enemy_zone'),
            ('set_flag', {'type':'set_flag','flag_id':'effect_flag','value':True}, 'flag'),
            ('reveal_clue', {'type':'reveal_clue','clue_id':'bell_silenced'}, 'clue'),
            ('spawn_object', {'type':'spawn_object','room_id':'entry','object_id':'bell'}, 'objects'),
            ('remove_object', {'type':'remove_object','room_id':'entry','object_id':'bell'}, 'objects'),
            ('open_exit', {'type':'open_exit','room_id':'entry','direction':'east'}, 'flags'),
            ('end_run', {'type':'end_run','state':'quit'}, 'terminal'),
            ('interrupt_intent', {'type':'interrupt_intent'}, 'intent'),
        )
        for name,effect,projection in cases:
            with self.subTest(effect=name):
                state=DelveState.new(self.pack,2,'fighter'); state.room_id='vault'; engine=Engine(self.pack,state)
                state.player['hp']=10
                if projection=='objects' and name=='spawn_object': state.present_objects['entry'].remove('bell')
                events=[]; engine._effects([_effect(effect,'$.effect')],events)
                if projection=='hp': self.assertNotEqual(state.player['hp'],10)
                elif projection=='clock': self.assertEqual(state.clocks['patrol'],1)
                elif projection=='player_zone': self.assertEqual(state.player['zone'],'far')
                elif projection=='enemy_zone': self.assertEqual(state.enemies['captain']['zone'],'far')
                elif projection=='flag': self.assertIn('effect_flag',state.flags)
                elif projection=='clue': self.assertIn('bell_silenced',state.known_clues)
                elif projection=='objects': self.assertEqual('bell' in state.present_objects['entry'], name=='spawn_object')
                elif projection=='flags': self.assertTrue(any(flag.startswith('__open_exit:') for flag in state.flags))
                elif projection=='terminal': self.assertEqual(state.terminal,'quit')
                elif projection=='intent': self.assertIsNone(state.enemies['captain']['current_intent_id'])

    def test_payoff_kill_checks_victory_and_random_is_private(self):
        self.s.flags.add('captain_route_known'); self.s.known_facts.append('captain_route')
        self.s.enemies['captain']['hp'] = 6; self.s.enemies['captain']['current_intent_id'] = 'smash'
        global_state = random.getstate()
        self.act('shove', 'captain')
        self.assertEqual(self.s.terminal, 'victory'); self.assertEqual(self.s.rng_draws, 0); self.assertEqual(random.getstate(), global_state)

    def test_hazard_kill_emits_enemy_defeated_before_victory(self):
        self.s.flags.add('captain_route_known')
        self.s.known_facts.append('captain_route')
        self.s.enemies['captain']['hp'] = 6
        self.s.enemies['captain']['current_intent_id'] = 'smash'
        events = self.act('shove', 'captain')
        keys = [event.key for event in events]
        self.assertLess(keys.index('hazard.collapse'), keys.index('enemy.defeated'))
        self.assertLess(keys.index('enemy.defeated'), keys.index('terminal.victory'))

    def test_mixed_action_fuzz_never_raises(self):
        chooser = random.Random(4)
        for seed in range(5):
            for sequence in range(100):
                s = DelveState.new(self.pack, seed * 100 + sequence, 'fighter'); s.room_id='vault'; s.player['zone']='doorway'; s.inventory=['clay_cup']
                e=Engine(self.pack,s); enemy=e._living_enemy(); s.event_log.append(e._event('intent.captain.smash', {'enemy_name':enemy.name}).to_dict())
                for _ in range(12):
                    verb=chooser.choice(('shove','throw','use','brace','attack','retreat'))
                    try: e.apply(Action(verb, chooser.choice(('captain','clay_cup')), chooser.choice(('west','north'))))
                    except Exception as exc: self.fail(f'seed {seed}, sequence {sequence}, {verb}: {exc!r}')
                    self.assertGreaterEqual(s.rng_draws, 0)
                    assert_telegraph(self, s.event_log)

    def test_non_shove_hazard_trigger_does_not_fire(self):
        d=copy.deepcopy(EXAMPLE); d['hazards']=[{'id':'other_hazard','room_id':'vault','zone':'hazard','tag':'collapse','event_key':'hazard.collapse','trigger':{'action':'move','requires_flag_id':None},'effects':[{'type':'damage','target':'enemy','amount':9}]}]
        with self.assertRaises(Exception) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_UNSUPPORTED_MECHANIC')

    def test_shove_uses_the_first_hazard_whose_gate_is_open(self):
        d=copy.deepcopy(EXAMPLE)
        d['rooms'][0]['objects'][0]['reader']['effects'].append({'type':'set_flag','flag_id':'hidden_route','value':True})
        d['hazards'].insert(0, {
            'id':'entry_fire', 'room_id':'vault', 'zone':'hazard', 'tag':'fire',
            'event_key':'hazard.fire',
            'trigger':{'action':'move','requires_flag_id':None},
            'effects':[{'type':'damage','target':'player','amount':1}],
        })
        d['bank']['entries'].append({'key':'hazard.fire','fact_slots':[],
                                     'variants':['Fire.'],'fallback':'Fire.'})
        d['hazards']=[
            *d['hazards'][:1],
            {'id':'locked_collapse','room_id':'vault','zone':'hazard','tag':'collapse','event_key':'hazard.collapse',
             'trigger':{'action':'shove','requires_flag_id':'hidden_route'},
             'effects':[{'type':'damage','target':'enemy','amount':1}]},
            {'id':'open_collapse','room_id':'vault','zone':'hazard','tag':'collapse','event_key':'hazard.collapse',
             'trigger':{'action':'shove','requires_flag_id':None},
             'effects':[{'type':'damage','target':'enemy','amount':7}]},
        ]
        pack=load_pack(d); state=DelveState.new(pack,3,'fighter'); state.room_id='vault'; state.player['zone']='doorway'
        engine=Engine(pack,state); state.enemies['captain']['current_intent_id']='smash'
        before=state.enemies['captain']['hp']
        engine.apply(Action('shove'))
        self.assertEqual(state.enemies['captain']['hp'],before-7)


if __name__ == '__main__': unittest.main()
