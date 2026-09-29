import copy
import ast
import json
import re
import random
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from dataclasses import FrozenInstanceError, replace

from delve import PackError, load_pack, validate_pack
from delve.pack import ENGINE_SLOTS, STRUCTURAL_KEYS, check_engine_ready, load_engine_ready_pack
from delve.commands import ParseProblem, parse_command
from delve.state import DelveState

SPEC = Path(__file__).parents[1] / 'docs' / 'DELVE_M1_SPEC.md'
TEXT = SPEC.read_text(encoding='utf-8')
EXAMPLE = json.loads(re.search(r'### Complete valid example\s*```json\s*(.*?)\s*```', TEXT, re.S).group(1))

def mutation(code):
    d=copy.deepcopy(EXAMPLE)
    if code=='E_EXIT_DANGLING': d['rooms'][0]['exits'][0]['to_room_id']='missing'
    elif code=='E_EFFECT_UNKNOWN': d['rooms'][0]['objects'][0]['reader']['effects'][0]={'type':'explode'}
    elif code=='E_TERMINAL_UNREACHABLE': d['terminals'][0]['all']=[{'kind':'room_is','room_id':'entry'}, {'kind':'room_is','room_id':'vault'}]
    elif code=='E_BANK_FALLBACK_MISSING': d['bank']['entries']=[e for e in d['bank']['entries'] if e['key']!='terminal.victory']
    elif code=='E_ATMOSPHERE_UNREGISTERED': d['rooms'][0]['objects'].append({'id':'mist_obj','name':'mist','zone':'near','atmosphere_only':True,'atmosphere_id':'mist'})
    elif code=='E_FACT_CLUE_COUNT': d['truth']['facts'][0]['clue_ids'].remove('dome_crack'); d['truth']['clues']=[c for c in d['truth']['clues'] if c['id']!='dome_crack']
    elif code=='E_ID_DUPLICATE': d['rooms'][0]['objects'][1]['id']='bell'
    elif code=='E_VERB_UNKNOWN': d['rooms'][0]['objects'][0]['reader']['on']='sing'
    elif code=='E_CLOCK_THRESHOLD_RANGE': d['clocks'][0]['thresholds'][0]['at']=5
    elif code=='E_INTENT_TELEGRAPH_MISSING': d['bank']['entries']=[e for e in d['bank']['entries'] if e['key']!='intent.captain.smash']
    elif code=='E_HAZARD_TAG_UNKNOWN': d['hazards'][0]['tag']='acid'
    elif code=='E_OBJECT_READER_MISSING': d['rooms'][0]['objects'][0].pop('reader')
    elif code=='E_ITEM_UNKNOWN': d['rooms'][0]['objects'][0]['item_id']='missing_item'
    elif code=='E_ITEM_DUPLICATE_SOURCE':
        d['items'].append({'id':'test_item','name':'test item','reader':{'on':'use','event_key':'object.read','effects':[]}})
        d['rooms'][0]['objects'][0]['item_id']='test_item'
        d['rooms'][0]['objects'][1]['item_id']='test_item'
    elif code=='E_BANK_FALLBACK_MISSING_TAKEABLE': d['rooms'][0]['objects'][0]['item_id']='test_item'; d['items'].append({'id':'test_item','name':'test item','reader':{'on':'use','event_key':'object.read','effects':[]}}); d['bank']['entries']=[e for e in d['bank']['entries'] if e['key']!='get.blocked']
    elif code=='E_ITEM_CONSUMED_TYPE': d['items'].append({'id':'test_item','name':'test item','reader':{'on':'use','event_key':'object.read','effects':[]},'consumed_on_use':'yes'})
    return d

class PackTests(unittest.TestCase):
    def test_valid_example_loads_equal_immutable(self):
        first=load_pack(EXAMPLE); second=load_pack(copy.deepcopy(EXAMPLE))
        self.assertEqual(first,second)
        with self.assertRaises(FrozenInstanceError): first.id='changed'

    def _reject(self,code):
        with self.assertRaises(PackError) as cm: load_pack(mutation(code))
        self.assertEqual(cm.exception.code,code)
        self.assertTrue(cm.exception.path)
        self.assertTrue(cm.exception.message)

    def test_E_EXIT_DANGLING(self): self._reject('E_EXIT_DANGLING')
    def test_E_EFFECT_UNKNOWN(self): self._reject('E_EFFECT_UNKNOWN')
    def test_E_TERMINAL_UNREACHABLE(self): self._reject('E_TERMINAL_UNREACHABLE')
    def test_E_BANK_FALLBACK_MISSING(self): self._reject('E_BANK_FALLBACK_MISSING')

    def test_named_missing_fallback_field_has_required_code(self):
        d=copy.deepcopy(EXAMPLE)
        next(e for e in d['bank']['entries'] if e['key']=='terminal.victory').pop('fallback')
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_BANK_FALLBACK_MISSING')

    def test_hazard_trigger_fields_are_strictly_typed(self):
        for value in (['bad'], {}, 1, True):
            d=copy.deepcopy(EXAMPLE); d['hazards'][0]['trigger']['requires_flag_id']=value
            with self.subTest(value=value), self.assertRaises(PackError): load_pack(d)
        d=copy.deepcopy(EXAMPLE); d['hazards'][0]['trigger']['requires_flag_id']=None
        self.assertIsNone(load_pack(d).hazards[0].trigger['requires_flag_id'])

    def test_predicate_fields_reject_wrong_types_as_pack_errors(self):
        for field,value in (('kind',['flag_set']),('flag_id',['bad'])):
            d=copy.deepcopy(EXAMPLE); d['terminals'][0]['all']=[{'kind':'flag_set','flag_id':'never_set'}]
            d['terminals'][0]['all'][0][field]=value
            with self.subTest(field=field), self.assertRaises(PackError): load_pack(d)

    def test_intent_and_threshold_effect_references_are_validated(self):
        for where in ('intent','threshold'):
            d=copy.deepcopy(EXAMPLE)
            effect={'type':'tick_clock','clock_id':'missing_clock','amount':1}
            if where=='intent': d['enemies'][0]['intents'][0]['effects'].append(effect)
            else: d['clocks'][0]['thresholds'][0]['effects'].append(effect)
            with self.subTest(where=where), self.assertRaises(PackError) as cm: load_pack(d)
            self.assertEqual(cm.exception.code,'E_SCHEMA')

    def test_engine_ready_rejects_unsupplied_bank_slots(self):
        for key in ('intent.captain.smash','object.read','clue.bell','hazard.collapse','get.blocked'):
            with self.subTest(key=key):
                d=self._engine_ready_dict()
                entry=next(e for e in d['bank']['entries'] if e['key']==key)
                entry.update(fact_slots=['phantom'], variants=['{{phantom}}'], fallback='{{phantom}}')
                with self.assertRaises(PackError) as cm: load_engine_ready_pack(d)
                self.assertEqual(cm.exception.code,'E_BANK_SLOT_UNSUPPLIED')

    def test_engine_ready_wrapper_rejects_missing_structural_key(self):
        d=self._engine_ready_dict()
        d['bank']['entries']=[e for e in d['bank']['entries'] if e['key']!='move.blocked']
        with self.assertRaises(PackError) as cm: load_engine_ready_pack(d)
        self.assertEqual(cm.exception.code,'E_BANK_STRUCTURAL_MISSING')

    def test_static_unreachable_victory_mutant_is_killed(self):
        d=copy.deepcopy(EXAMPLE)
        d['terminals'][0]['all']=[{'kind':'room_is','room_id':'entry'}, {'kind':'room_is','room_id':'vault'}]
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_TERMINAL_UNREACHABLE')

    def test_flag_predicates_and_unrevealed_clues_are_rejected(self):
        d=copy.deepcopy(EXAMPLE)
        d['terminals'][0]['all']=[{'kind':'flag_set','flag_id':'never_set'}]
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_FLAG_UNSETTABLE')
        d=copy.deepcopy(EXAMPLE)
        d['rooms'][0]['objects'][2]['reader']['effects']=[]
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_CLUE_UNREVEALABLE')

    def test_victory_end_run_is_rejected_in_nonterminal_effects(self):
        for where in ('reader','hazard','intent','threshold'):
            d=copy.deepcopy(EXAMPLE); effect={'type':'end_run','state':'victory'}
            if where=='reader': d['rooms'][0]['objects'][0]['reader']['effects'].append(effect)
            elif where=='hazard': d['hazards'][0]['effects'].append(effect)
            elif where=='intent': d['enemies'][0]['intents'][0]['effects'].append(effect)
            else: d['clocks'][0]['thresholds'][0]['effects'].append(effect)
            with self.subTest(where=where):
                with self.assertRaises(PackError) as cm: load_pack(d)
                self.assertEqual(cm.exception.code,'E_UNSUPPORTED_MECHANIC')

    def test_inert_fire_and_collapse_hazards_are_rejected(self):
        for tag,effects in (('fire',[]),('collapse',[])):
            d=copy.deepcopy(EXAMPLE); d['hazards'][0].update(tag=tag,effects=effects)
            d['hazards'][0]['trigger']={'action':'move' if tag=='fire' else 'shove','requires_flag_id':None}
            with self.subTest(tag=tag), self.assertRaises(PackError) as cm: load_pack(d)
            self.assertEqual(cm.exception.code,'E_UNSUPPORTED_MECHANIC')

    def test_engine_readiness_wrapper_is_the_terminal_loader(self):
        from delve import __main__ as terminal
        import contextlib
        import io
        d=self._engine_ready_dict()
        d['bank']['entries']=[e for e in d['bank']['entries'] if e['key']!='move.blocked']
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'not_ready.json'; path.write_text(json.dumps(d),encoding='utf-8')
            output=io.StringIO()
            with contextlib.redirect_stdout(output), patch('builtins.input',side_effect=AssertionError('terminal began play')):
                code=terminal.main(['--pack',str(path),'--class','fighter'])
            self.assertEqual(code,2)
            self.assertIn('E_BANK_STRUCTURAL_MISSING',output.getvalue())

    def test_shipped_pack_500_mutants_are_rejected_or_survive_random_sessions(self):
        shipped=json.loads((Path(__file__).parents[1]/'delve'/'content'/'mossy_fast_slice.json').read_text())
        rng=random.Random(17000)
        mutations=('trigger_flag','effect_amount','reader_flag','hazard_tag','effect_type','enemy_zone',
                   'room_zone','clock_threshold','bank_slots','flag_predicate','empty_cycle','description_type')
        actions=('look','inventory','help','get','use','attack','shove','brace','throw','move','retreat','quit')
        for index in range(500):
            d=copy.deepcopy(shipped); choice=rng.choice(mutations)
            invalid_value=rng.choice((['bad'], {'bad':1}, 7, True))
            if choice=='trigger_flag': d['hazards'][0]['trigger']['requires_flag_id']=invalid_value
            elif choice=='effect_amount': d['hazards'][0]['effects'][0]['amount']=invalid_value
            elif choice=='reader_flag': d['rooms'][0]['objects'][0]['reader']['when_flag_id']=invalid_value
            elif choice=='hazard_tag': d['hazards'][0]['tag']=invalid_value
            elif choice=='effect_type': d['rooms'][0]['objects'][0]['reader']['effects'][0]['type']=invalid_value
            elif choice=='enemy_zone': d['enemies'][0]['start_zone']=invalid_value
            elif choice=='room_zone': d['rooms'][0]['zones']=['near', []]
            elif choice=='clock_threshold': d['clocks'][0]['thresholds'][0]['at']=['bad']
            elif choice=='bank_slots':
                entry=next(e for e in d['bank']['entries'] if e['key']=='intent.goblin.strike')
                entry.update(fact_slots=['phantom'],variants=['{{phantom}}'],fallback='{{phantom}}')
            elif choice=='flag_predicate': d['terminals'][0]['all']=[{'kind':'flag_set','flag_id':['bad']}]
            elif choice=='empty_cycle': d['enemies'][0]['intent_cycle']=[]
            elif choice=='description_type': d['rooms'][0]['description_key']=[]
            try: pack=load_engine_ready_pack(d)
            except PackError: continue
            from delve.engine import Action, Engine
            from delve.state import DelveState
            state=DelveState.new(pack,index,'fighter'); engine=Engine(pack,state); chooser=random.Random(9000+index)
            try:
                for _ in range(60):
                    verb=chooser.choice(actions)
                    engine.apply(Action(verb, target_id=chooser.choice(('brass_ring','goblin','missing','brass_ring_obj')),
                                        direction=chooser.choice(('north','south','east','west'))))
            except Exception as exc:
                self.fail(f'mutant {index} ({choice}) accepted then crashed: {exc!r}')
    def test_E_ATMOSPHERE_UNREGISTERED(self): self._reject('E_ATMOSPHERE_UNREGISTERED')
    def test_E_FACT_CLUE_COUNT(self): self._reject('E_FACT_CLUE_COUNT')
    def test_E_ID_DUPLICATE(self): self._reject('E_ID_DUPLICATE')
    def test_E_VERB_UNKNOWN(self): self._reject('E_VERB_UNKNOWN')
    def test_E_CLOCK_THRESHOLD_RANGE(self): self._reject('E_CLOCK_THRESHOLD_RANGE')
    def test_E_INTENT_TELEGRAPH_MISSING(self): self._reject('E_INTENT_TELEGRAPH_MISSING')
    def test_E_HAZARD_TAG_UNKNOWN(self): self._reject('E_HAZARD_TAG_UNKNOWN')
    def test_E_OBJECT_READER_MISSING(self): self._reject('E_OBJECT_READER_MISSING')

    def test_E_ITEM_UNKNOWN(self): self._reject('E_ITEM_UNKNOWN')
    def test_E_ITEM_DUPLICATE_SOURCE(self): self._reject('E_ITEM_DUPLICATE_SOURCE')
    def test_consumed_on_use_must_be_boolean(self):
        with self.assertRaises(PackError) as cm: load_pack(mutation('E_ITEM_CONSUMED_TYPE'))
        self.assertEqual(cm.exception.code, 'E_SCHEMA')

    def test_consumed_on_use_defaults_false(self):
        d=copy.deepcopy(EXAMPLE)
        d['items'].append({'id':'test_item','name':'test item','reader':{'on':'use','event_key':'object.read','effects':[]}})
        self.assertFalse(load_pack(d).items[0].consumed_on_use)

    def test_parser_problems_are_bank_events_with_slots(self):
        pack=load_pack(EXAMPLE); state=DelveState.new(pack,1,'fighter')
        unknown=parse_command('look moon rock',state,pack)
        self.assertIsInstance(unknown,ParseProblem)
        self.assertEqual((unknown.message_key,unknown.fact_slots),('target.unknown',{'target':'moon rock'}))
        state.room_id='entry'
        from delve.model import GameObject, Reader
        room=next(r for r in pack.rooms if r.id=='entry')
        expanded=replace(room,objects=room.objects+(GameObject('stone_compass','stone compass','near',Reader('look','object.read',())),))
        pack=replace(pack,rooms=tuple(expanded if r.id=='entry' else r for r in pack.rooms))
        state.present_objects['entry'].append('stone_compass')
        ambiguous=parse_command('look s',state,pack)
        self.assertEqual(ambiguous.message_key,'target.ambiguous')
        self.assertEqual(ambiguous.fact_slots['candidates'],'star chart, stone compass')
        verb=parse_command('dance',state,pack)
        self.assertEqual((verb.message_key,verb.fact_slots),('parse.unknown_verb',{'verb':'dance'}))
    def test_takeable_object_requires_interaction_fallbacks(self):
        with self.assertRaises(PackError) as cm: load_pack(mutation('E_BANK_FALLBACK_MISSING_TAKEABLE'))
        self.assertEqual(cm.exception.code,'E_BANK_FALLBACK_MISSING')

    def test_takeable_object_loads_with_item_and_fallbacks(self):
        d=copy.deepcopy(EXAMPLE)
        d['items'].append({'id':'test_item','name':'test item','reader':{'on':'use','event_key':'object.read','effects':[]}})
        d['rooms'][0]['objects'][0]['item_id']='test_item'
        for key in ('get.blocked','get.not_takeable','use.nothing'):
            d['bank']['entries'].append({'key':key,'fact_slots':[],'variants':[],'fallback':'Nothing happens.'})
        self.assertEqual(load_pack(d).rooms[0].objects[0].item_id,'test_item')

    def test_unknown_fields_wrong_types_and_formats(self):
        d=copy.deepcopy(EXAMPLE); d['rogue']=1
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_SCHEMA')
        d=copy.deepcopy(EXAMPLE); d['rooms'][0]['mystery']=1
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_SCHEMA')
        d=copy.deepcopy(EXAMPLE); d['schema_version']='1'
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_SCHEMA')

    def test_unique_reachable_clue_sources(self):
        d=copy.deepcopy(EXAMPLE); d['truth']['facts'][0]['clue_ids']=d['truth']['facts'][0]['clue_ids'][:2]; d['truth']['clues'].pop()
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_FACT_CLUE_COUNT')
        d=copy.deepcopy(EXAMPLE)
        for c in d['truth']['clues']: c['source_id']='bell'
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_FACT_CLUE_COUNT')

    def test_clue_source_unreachable(self):
        d=copy.deepcopy(EXAMPLE); d['rooms'][0]['exits']=[]
        d['rooms'][1]['objects'].append(d['rooms'][0]['objects'].pop(0))
        d['truth']['clues'][0]['room_id']='vault'
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_FACT_CLUE_COUNT')

    def test_placeholder_slots_must_match(self):
        d=copy.deepcopy(EXAMPLE); d['bank']['entries'][2]['fact_slots']=[]
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_BANK_SLOT')

    def test_semantics_are_more_than_json_parsing(self):
        d=copy.deepcopy(EXAMPLE); d['rooms'][0]['exits'][0]['to_room_id']='missing'
        with self.assertRaises(PackError) as cm: validate_pack(load_unvalidated(d))
        self.assertEqual(cm.exception.code,'E_EXIT_DANGLING')

    def test_accepts_path_json_text_and_dict(self):
        self.assertEqual(load_pack(EXAMPLE),load_pack(json.dumps(EXAMPLE)))
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'pack.json'; p.write_text(json.dumps(EXAMPLE),encoding='utf-8')
            self.assertEqual(load_pack(p),load_pack(EXAMPLE))
        with self.assertRaises(PackError) as cm: load_pack('{')
        self.assertEqual(cm.exception.code,'E_SCHEMA'); self.assertEqual(cm.exception.path,'$')

    def _engine_ready_dict(self):
        d=copy.deepcopy(EXAMPLE)
        d['items'].append({'id':'test_item','name':'test item','reader':{'on':'throw','event_key':'item.throwread','effects':[]}})
        d['rooms'][0]['objects'][0]['item_id']='test_item'
        keys=set(STRUCTURAL_KEYS)
        keys.add('item.throwread')
        keys.update(('get.blocked','get.not_takeable','use.nothing'))
        for key in keys:
            if key not in {e['key'] for e in d['bank']['entries']}:
                d['bank']['entries'].append({'key':key,'fact_slots':[],'variants':[],'fallback':'Fallback.'})
        return d

    def test_complete_synthetic_pack_is_engine_ready(self):
        d=self._engine_ready_dict()
        self.assertEqual(load_engine_ready_pack(d),load_pack(d))
        self.assertIsNone(check_engine_ready(load_pack(d)))

    def test_each_applicable_structural_key_is_required(self):
        d=self._engine_ready_dict()
        ready=load_pack(d)
        applicable=[]
        for key, condition in STRUCTURAL_KEYS.items():
            active={
                'always':True, 'enemies':bool(d['enemies']),
                'takeable_objects':any(o.get('item_id') for r in d['rooms'] for o in r['objects']),
                'items':bool(d['items']), 'hazards':bool(d['hazards']),
                'facts':bool(d['truth']['facts']), 'clocks':bool(d['clocks']),
                'thresholds':any(c['thresholds'] for c in d['clocks']),
            }[condition]
            if active: applicable.append(key)
        for key in applicable:
            with self.subTest(key=key):
                removed={key}
                if key=='clock.threshold': removed.add('clock.threshold.patrol.2')
                broken=replace(ready,bank=tuple(e for e in ready.bank if e.key not in removed))
                with self.assertRaises(PackError) as cm:
                    check_engine_ready(broken)
                self.assertEqual(cm.exception.code,'E_BANK_STRUCTURAL_MISSING')
                named=key
                if key=='clock.threshold': named='clock.threshold.patrol.2'
                self.assertIn(named,cm.exception.message)
        broken=replace(ready,bank=tuple(e for e in ready.bank if e.key!='item.throwread'))
        with self.assertRaises(PackError) as cm:
            check_engine_ready(broken)
        self.assertEqual(cm.exception.code,'E_BANK_STRUCTURAL_MISSING')
        self.assertIn('item.throwread',cm.exception.message)

    def test_clock_threshold_specific_or_generic_key(self):
        d=self._engine_ready_dict()
        d['bank']['entries']=[e for e in d['bank']['entries'] if e['key']!='clock.threshold']
        d['bank']['entries'].append({'key':'clock.threshold.patrol.2','fact_slots':['at','clock_label'],'variants':['At {{at}}: {{clock_label}}.'],'fallback':'At {{at}}: {{clock_label}}.'})
        pack=load_pack(d)
        pack=replace(pack,bank=tuple(e for e in pack.bank if e.key!='clock.threshold'))
        check_engine_ready(pack)

    def test_engine_event_literals_stay_covered(self):
        source=(Path(__file__).parents[1]/'delve'/'engine.py').read_text(encoding='utf-8')
        emitted=set(re.findall(r"_event\(\s*['\"]([^'\"]+)['\"]",source))
        self.assertTrue(emitted)
        emitted.discard('terminal.')  # Dynamic terminal suffix is checked explicitly below.
        self.assertEqual(emitted-set(STRUCTURAL_KEYS),set())
        for suffix in ('victory','death','closed'):
            self.assertIn('terminal.'+suffix,STRUCTURAL_KEYS)
        self.assertNotIn('combat.not_yet', STRUCTURAL_KEYS)  # Amendment 4 item 8 retires this key.
        self.assertTrue({'enemy.defeated','target.ambiguous','parse.unknown_verb'} <= STRUCTURAL_KEYS.keys())
        self.assertEqual(set(ENGINE_SLOTS),set(STRUCTURAL_KEYS))
        self.assertEqual(ENGINE_SLOTS['intent.cancelled'],{'enemy_name'})
        self.assertEqual(ENGINE_SLOTS['get.blocked'],{'enemy_name'})
        self.assertEqual(ENGINE_SLOTS['item.get'],{'item_name'})
        observed={}
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Attribute) or node.func.attr!='_event': continue
            if not node.args or not isinstance(node.args[0],ast.Constant) or not isinstance(node.args[0].value,str): continue
            key=node.args[0].value
            if len(node.args)>1 and isinstance(node.args[1],ast.Dict):
                observed.setdefault(key,set()).update(k.value for k in node.args[1].keys if isinstance(k,ast.Constant))
            else: observed.setdefault(key,set())
        for key,slots in observed.items():
            self.assertIn(key,ENGINE_SLOTS,key)
            self.assertTrue(slots.issubset(ENGINE_SLOTS[key]),(key,slots,ENGINE_SLOTS[key]))

# Exercise semantic validation independently of the strict public loader.
def load_unvalidated(d):
    from delve.pack import _parse
    return _parse(d)

if __name__=='__main__': unittest.main()
