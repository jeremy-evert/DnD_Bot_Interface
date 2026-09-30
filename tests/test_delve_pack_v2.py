"""M2.1 shared-contract boundary and mutation gate."""
import copy
import hashlib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from delve import model
from delve.pack import PackError, event_manifest, load_pack, pack_receipt, validate_pack

ROOT = Path(__file__).parents[1]
SPEC = ROOT / 'docs' / 'DELVE_M2_SPEC.md'


def v2_example():
    selectors = list(model.V2_SELECTORS)
    def intent(ident,kind,target,event_key,damage=0,destination=None,roll=False):
        consequences=model.V2_INTENT_CONSEQUENCES
        slots={
            'strike':['actor_name','target_name','damage'],
            'ranged':['actor_name','target_name','damage'],
            'feed':['actor_name','target_name','damage'],
            'move':['actor_name','destination_name'],
            'flee':['actor_name','destination_name'],
            'guard':['actor_name'], 'hold_position':['actor_name'],
        }[kind]
        result={'id':ident,'kind':kind,'selector':'visible_actor','target':target,
                'damage':damage,'roll':roll,'consequence':consequences[kind],
                'event_key':event_key,'cancel_event_key':'actor.intent.cancelled','fact_slots':slots}
        if destination is not None: result['destination']=destination
        return result
    d = {
        'schema_version': 2, 'id': 'menagerie_example', 'title': 'The Sundered Menagerie',
        'start_room_id': 'gate',
        'rooms': [
            {'id': 'gate', 'title': 'Broken Gate', 'exits': ['balcony'], 'tags': []},
            {'id': 'balcony', 'title': 'Mira’s Balcony', 'exits': ['gate'], 'tags': []},
        ],
        'actors': [
            {'id': 'drake', 'room_id': 'gate', 'zone': 'far', 'stats': {'hp': 18, 'armor_class': 14},
             'faction': 'predator', 'initiative': 8, 'state': 'hungry', 'inactive_state': 'sleeping', 'ecology_profile':'kiln_drake',
             'intents': [
                 intent('feed', 'feed', 'living_prey', 'intent.drake.feed', 8),
                 intent('flee', 'flee', 'safe_destination', 'intent.drake.flee', destination='balcony'),
                 intent('move', 'move', 'connected_zone', 'intent.drake.move', destination='near'),
                 intent('hold', 'hold_position', 'zone', 'intent.drake.hold', destination='far'),
             ],
             'appetite': ['hungry', 'scented_prey'], 'fears': ['bright', 'crush'], 'aggro': ['retaliate_last_attacker'], 'tags': []},
            {'id': 'goblin_hook', 'room_id': 'gate', 'zone': 'doorway', 'stats': {'hp': 8, 'armor_class': 12},
             'faction': 'goblin', 'initiative': 4, 'state': 'guarding', 'ecology_profile':'banquet_goblin',
             'intents': [
                 intent('hook_strike', 'strike', 'visible_actor', 'intent.goblin.hook', 2),
                 intent('hook_guard', 'guard', 'zone', 'intent.goblin.guard'),
             ],
             'appetite': [], 'fears': ['bright'], 'aggro': ['guard_exit', 'strike_intruder']},
            {'id': 'goblin_slinger', 'room_id': 'gate', 'zone': 'far', 'stats': {'hp': 7, 'armor_class': 12},
             'faction': 'goblin', 'initiative': 3, 'state': 'guarding', 'ecology_profile':'banquet_goblin',
             'intents': [
                 intent('sling', 'ranged', 'visible_actor', 'intent.goblin.slinger', 2),
                 intent('sling_player', 'ranged', 'visible_actor', 'intent.goblin.slinger_player', 2),
             ],
             'appetite': [], 'fears': ['bright'], 'aggro': ['guard_food', 'return_to_post']},
        ],
        'objects': [
            {'id': 'supper_table', 'room_id': 'gate', 'zone': 'near', 'tags': ['flammable','oiled']},
            {'id': 'map_object', 'room_id': 'gate', 'zone': 'far', 'tags': ['flammable','fragile']},
            {'id': 'awning', 'room_id': 'gate', 'zone': 'doorway', 'tags': ['wet']},
        ],
        'materials': [
            {'id': 'oil_table', 'room_id': 'gate', 'zone': 'near', 'tags': ['oiled', 'flammable'], 'object_id': 'supper_table'},
            {'id': 'wet_awning', 'room_id': 'gate', 'zone': 'doorway', 'tags': ['wet']},
            {'id': 'silk_map', 'room_id': 'gate', 'zone': 'far', 'tags': ['flammable', 'fragile']},
        ],
        'reaction_table': [], 'reaction_order': ['R5','R6','R1','R2','R4','R3','R8','R9','R11'],
        'reaction_step_limit': 3, 'selectors': selectors, 'class_actions': [],
        'inventory_items': ['brass_case'], 'outcome_flags': ['exit_open'],
        'terminals': [
            {'id': 'victory', 'kind': 'victory', 'all': [
                {'kind': 'room_is', 'room_id': 'balcony'}, {'kind': 'inventory_has', 'item_id': 'brass_case'}], 'event_key': 'terminal.victory'},
            {'id': 'death', 'kind': 'death', 'all': [{'kind': 'outcome_state', 'state': 'death'}], 'event_key': 'terminal.death'},
        ],
        'chains': [{'id': 'scent_hunt_feed', 'event_keys': ['chain.scent.hunt.feed'], 'minimum_effect': 1, 'step_limit': 3}],
        'ecology': {'profiles': [
            {'id': 'kiln_drake', 'priority': ['finish_declared_bite','flee_announced_crush','pursue_scented_living_prey','consume_loose_edible_bait','retaliate_last_attacker','digest_two_beats','sleep_sated'], 'event_key': 'ecology.drake', 'fact_slots': ['actor_name']},
            {'id': 'banquet_goblin', 'priority': ['flee_drake_in_zone','guard_assigned_food_or_exit','strike_reachable_intruder','return_to_post'], 'event_key': 'ecology.goblin', 'fact_slots': ['actor_name']},
        ]},
        'chronicle': {'event_keys': ['chronicle.signature']}, 'bank': {'entries': []},
    }
    names = ('oil_flash','ignition','damp_heat','fire_spread','extinguish','break','drop','sound','appetite','feeding','fear','sight')
    signals = ('heat','heat','heat','heat','water','impact','impact','sound',None,None,None,None)
    for i, (name, signal) in enumerate(zip(names, signals), 1):
        rid = f'R{i}'
        d['reaction_table'].append({'id': rid, 'name': name, 'signal': signal,
            'selector': 'zone' if 'zone' in selectors else selectors[0], 'fuel': 1,
            'event_key': f'material.{rid.lower()}.{name}', 'fact_slots': []})
    abilities = (
        ('fighter.hold_door','fighter','h','momentum',{'doorway':True},0,[{'type':'stance','beats':2,'selector':'actors_in_zone'}]),
        ('rogue.lure','rogue','l','trick',{'named_target':True},0,[{'type':'add_tag','selector':'named_actor','tag':'scented'},{'type':'move_actor','selector':'player','destination':'adjacent'}]),
        ('wizard.fireball','wizard','f','spark',{'visible_zone':True,'confirmation':True},0,[{'type':'damage_selector','selector':'actors_in_zone','amount':8},{'type':'signal','selector':'zone','kind':'heat'},{'type':'signal','selector':'zone','kind':'sound'}]),
    )
    for aid, cls, key, resource, requires, cooldown, effects in abilities:
        scope = 'delve' if resource == 'spark' else ('room' if resource == 'trick' else 'encounter')
        maximum = {'spark':1,'trick':2,'momentum':3}[resource]
        d['class_actions'].append({'id':aid,'class_id':cls,'key':key,'resource':{'kind':resource,'scope':scope,'cost':1,'maximum':maximum},
                                   'preconditions':requires,'cooldown':cooldown,'effects':effects,'event_key':'ability.'+aid})
    provisional = copy.deepcopy(d)
    # Manifest has fixed structural and declared content events. Build the bank
    # from the same public producer after validation-independent declarations.
    from delve.pack import _v2_event_manifest_data
    for event in _v2_event_manifest_data(provisional)['events']:
        slots=event['fact_slots']; text=' '.join('{{'+s+'}}' for s in slots) or 'The world remembers.'
        d['bank']['entries'].append({'key':event['key'],'fact_slots':slots,'variants':[text],'fallback':text})
    return d


class DelvePackV2Tests(unittest.TestCase):
    def test_example_loads_manifest_and_receipt_are_stable(self):
        pack=load_pack(v2_example())
        committed=load_pack(ROOT/'delve/content/v2_example.json') if (ROOT/'delve/content/v2_example.json').exists() else pack
        self.assertEqual(committed,pack)
        manifest=event_manifest(pack)
        self.assertEqual(manifest['events'], sorted(manifest['events'], key=lambda row: row['key']))
        expected_keys={'ability.fighter.hold_door','ability.rogue.lure','ability.wizard.fireball','actor.intent.cancelled','chain.scent.hunt.feed',
            'chronicle.line','chronicle.signature','ecology.drake','ecology.goblin','enemy.defeated','intent.cancelled',
            'intent.drake.feed','intent.drake.flee','intent.drake.move','intent.drake.hold',
            'intent.goblin.hook','intent.goblin.guard','intent.goblin.slinger','intent.goblin.slinger_player','material.r1.oil_flash','material.r2.ignition',
            'material.r3.damp_heat','material.r4.fire_spread','material.r5.extinguish','material.r6.break','material.r7.drop',
            'material.r8.sound','material.r9.appetite','material.r10.feeding','material.r11.fear','material.r12.sight',
            'material.reaction','move.blocked','move.no_exit','room.description','room.enter','room.return','target.unknown',
            'terminal.closed','terminal.death','terminal.quit','terminal.victory'}
        self.assertEqual({row['key'] for row in manifest['events']},expected_keys)
        self.assertEqual(next(row for row in manifest['events'] if row['key']=='actor.intent.cancelled')['fact_slots'],
                         ['actor_name','target_name'])
        slots_by_key={row['key']:row['fact_slots'] for row in manifest['events']}
        self.assertEqual(slots_by_key['intent.drake.feed'],['actor_name','damage','target_name'])
        self.assertEqual(slots_by_key['intent.goblin.hook'],['actor_name','damage','target_name'])
        self.assertEqual(slots_by_key['intent.drake.flee'],['actor_name','destination_name'])
        self.assertEqual(slots_by_key['intent.goblin.guard'],['actor_name'])
        self.assertEqual(slots_by_key['intent.drake.hold'],['actor_name'])
        self.assertEqual({intent['kind'] for actor in pack.as_dict()['actors'] for intent in actor['intents']},
                         set(model.V2_INTENT_KINDS))
        self.assertEqual(manifest['manifest_hash'],'eb64a9c899fc17fb0215a4587bb6e890b5e964c4fd4f4f1fd6f8229ebc2bba11')
        self.assertEqual(manifest['extra_bank_keys'],[])
        self.assertEqual(manifest['manifest_hash'], event_manifest(load_pack(v2_example()))['manifest_hash'])
        receipt=pack_receipt(pack)
        self.assertEqual(receipt['manifest_hash'], manifest['manifest_hash'])
        self.assertEqual(receipt['route_classifier_version'],'unbuilt')
        self.assertEqual(receipt['tag_rule_version'],'m2-r1-r12-v1')

    def test_v1_shipped_and_complete_spec_example_stay_v1(self):
        shipped=load_pack(ROOT/'delve/content/mossy_fast_slice.json')
        self.assertEqual(shipped.schema_version,1)
        # The complete M1 spec example is included from its canonical fenced JSON.
        source=(ROOT/'docs/DELVE_M1_SPEC.md').read_text(encoding='utf-8')
        match=re.search(r'### Complete valid example\s+```json\s+(.*?)\s+```',source,re.S)
        self.assertIsNotNone(match)
        example=json.loads(match.group(1))
        loaded=load_pack(example)
        self.assertEqual(loaded,load_pack(json.dumps(example)))

    def test_manifest_bank_coverage_is_exact_for_generated_keys(self):
        d=v2_example(); p=load_pack(d); expected={e['key']:e['fact_slots'] for e in event_manifest(p)['events']}
        self.assertTrue(set(expected)<= {entry['key'] for entry in d['bank']['entries']})
        extra=copy.deepcopy(d); extra['bank']['entries'].append({'key':'extra.author.note','fact_slots':[],'variants':['extra'],'fallback':'extra'})
        self.assertEqual(event_manifest(load_pack(extra))['manifest_hash'],event_manifest(p)['manifest_hash'])
        self.assertEqual(event_manifest(load_pack(extra))['extra_bank_keys'],['extra.author.note'])
        for mutate,code in (
            (lambda x: x['bank']['entries'].pop(), 'E_BANK_MANIFEST_MISSING'),
            (lambda x: x['bank']['entries'][0].update(fact_slots=['actor_name'],variants=['{{actor_name}}'],fallback='{{actor_name}}'), 'E_BANK_MANIFEST_SLOTS'),
            (lambda x: x['bank']['entries'][0].update(fallback='  '), 'E_BANK_MANIFEST_FALLBACK'),
        ):
            bad=copy.deepcopy(d); mutate(bad)
            with self.assertRaises(PackError) as cm: load_pack(bad)
            self.assertEqual(cm.exception.code,code)
        bad=copy.deepcopy(d)
        entry=next(e for e in bad['bank']['entries'] if e['key']=='intent.drake.feed')
        entry.update(fact_slots=['actor_name'],variants=['{{actor_name}}'],fallback='{{actor_name}}')
        with self.assertRaises(PackError) as cm: load_pack(bad)
        self.assertEqual(cm.exception.code,'E_BANK_MANIFEST_SLOTS')

    def test_mutation_gate_all_declared_boundary_values(self):
        base=v2_example(); tried=0; rejected=0
        cases=[]
        def at(path, replacement):
            def change(obj):
                node=obj
                for part in path[:-1]: node=node[part]
                node[path[-1]]=replacement
            cases.append((path,change))
        # Every generated event-key field and every corresponding bank key.
        for i,_ in enumerate(base['actors']):
            for j,_ in enumerate(base['actors'][i]['intents']): at(('actors',i,'intents',j,'event_key'),'invented.event')
        for i,_ in enumerate(base['reaction_table']): at(('reaction_table',i,'event_key'),'invented.event')
        for i,_ in enumerate(base['class_actions']): at(('class_actions',i,'event_key'),'invented.event')
        for i,_ in enumerate(base['terminals']): at(('terminals',i,'event_key'),'invented.event')
        for i,_ in enumerate(base['chains']): at(('chains',i,'event_keys'),['invented.event'])
        for i,_ in enumerate(base['ecology']['profiles']): at(('ecology','profiles',i,'event_key'),'invented.event')
        at(('chronicle','event_keys'),['invented.event'])
        for i,_ in enumerate(base['reaction_table']): at(('reaction_table',i,'fact_slots'),['phantom_slot'])
        for i,_ in enumerate(base['actors']): at(('actors',i,'intents',0,'fact_slots'),['phantom_slot'])
        for i,_ in enumerate(base['ecology']['profiles']): at(('ecology','profiles',i,'fact_slots'),['phantom_slot'])
        for i,entry in enumerate(base['bank']['entries']):
            at(('bank','entries',i,'key'),'mutated.bank.key')
            if entry['fact_slots']:
                at(('bank','entries',i,'fact_slots'),['phantom_slot'])
        for i,tag in enumerate(model.MATERIAL_TAGS): at(('materials',0,'tags'),[tag,'unknown_tag'])
        for tag in model.MATERIAL_TAGS:
            at(('objects',0,'tags'),[tag,'unknown_tag'])
            at(('actors',0,'tags'),[tag,'unknown_tag'])
            at(('rooms',0,'tags'),[tag,'unknown_tag'])
        for i,_ in enumerate(base['reaction_table']):
            at(('reaction_table',i,'signal'),'scent')
            at(('reaction_table',i,'fuel'),True)
        for i,_ in enumerate(base['selectors']): at(('selectors',i),'__import__(os)')
        at(('actors',0,'intents',0,'selector'),'unknown_selector')
        for i,_ in enumerate(base['class_actions']): at(('class_actions',i,'effects',0,'selector'),'unknown_selector')
        for i,a in enumerate(base['class_actions']): at(('class_actions',i,'resource','kind'),'legend')
        for i,kind in enumerate(model.V2_RESOURCES): at(('class_actions',2,'resource','kind'),'unknown_'+kind)
        for i,a in enumerate(base['class_actions']): at(('class_actions',i,'id'),'wizard.freeform')
        at(('class_actions',1,'id'),'fighter.hold_door')  # duplicate/foreign closed ID
        for path,change in cases:
            bad=copy.deepcopy(base); change(bad); tried+=1
            try: load_pack(bad)
            except PackError as exc:
                self.assertTrue(exc.code.startswith(('E_')), (path,exc.code)); rejected+=1
            else: self.fail(f'mutation accepted: {path}')
        # An isolated bank rename cannot alter the generated manifest and is rejected.
        bad=copy.deepcopy(base); bad['bank']['entries'][0]['key']='changed.only.in.bank'; tried+=1
        with self.assertRaises(PackError) as cm: load_pack(bad)
        self.assertTrue(cm.exception.code.startswith('E_BANK_MANIFEST_')); rejected+=1
        self.assertGreaterEqual(tried,200)
        self.assertEqual(tried,rejected)
        print(f'M2 mutation gate: {tried} mutations tried, {rejected} rejected')
        self.mutation_counts=(tried,rejected)

    def test_intent_contract_mutations_have_coded_rejections(self):
        cases=(
            ('unknown kind',lambda d:d['actors'][0]['intents'][0].update(kind='summon'), 'E_V2_INTENT'),
            ('target type',lambda d:d['actors'][0]['intents'][0].update(target=['player']), 'E_SCHEMA'),
            ('unknown target',lambda d:d['actors'][0]['intents'][0].update(target='enemy_everywhere'), 'E_V2_SELECTOR'),
            ('damage type',lambda d:d['actors'][0]['intents'][0].update(damage=True), 'E_SCHEMA'),
            ('negative damage',lambda d:d['actors'][0]['intents'][0].update(damage=-1), 'E_SCHEMA'),
            ('roll type',lambda d:d['actors'][0]['intents'][0].update(roll=1), 'E_SCHEMA'),
            ('roll actor target',lambda d:d['actors'][0]['intents'][0].update(roll=True), 'E_V2_INTENT'),
            ('destination on attack',lambda d:d['actors'][0]['intents'][0].update(destination='near'), 'E_V2_INTENT'),
            ('missing move destination',lambda d:d['actors'][0]['intents'][0].update(kind='move',consequence='move',
                 fact_slots=['actor_name','destination_name']), 'E_V2_INTENT'),
            ('wrong destination',lambda d:d['actors'][0]['intents'][1].update(destination='unknown_zone'), 'E_V2_REFERENCE'),
            ('unknown consequence',lambda d:d['actors'][0]['intents'][0].update(consequence='spawn'), 'E_V2_INTENT'),
            ('unknown cancel key',lambda d:d['actors'][0]['intents'][0].update(cancel_event_key='invented.cancel.event'), 'E_BANK_MANIFEST_MISSING'),
            ('malformed cancel key',lambda d:d['actors'][0]['intents'][0].update(cancel_event_key='BAD KEY'), 'E_SCHEMA'),
        )
        for label,mutate,code in cases:
            d=v2_example(); mutate(d)
            with self.subTest(label=label), self.assertRaises(PackError) as cm:
                load_pack(d)
            self.assertEqual(cm.exception.code,code)
        # A player-target attack can opt into the M1 two-draw rule.
        d=v2_example(); attack=d['actors'][2]['intents'][1]
        attack['target']='player'; attack['roll']=True
        self.assertIsInstance(load_pack(d),model.V2Pack)

    def test_hash_is_process_stable_and_manifest_relevant_changes_hash(self):
        d=v2_example(); expected=event_manifest(load_pack(d))['manifest_hash']
        script="from tests.test_delve_pack_v2 import v2_example; from delve.pack import load_pack,event_manifest; print(event_manifest(load_pack(v2_example()))['manifest_hash'])"
        result=subprocess.check_output([sys.executable,'-c',script],cwd=ROOT,text=True).strip()
        self.assertEqual(expected,result)
        d['actors'][0]['intents'][0]['event_key']='intent.drake.bite_changed'
        with self.assertRaises(PackError): load_pack(d)
        d=v2_example(); d['actors'][0]['intents'][0]['fact_slots']=[]
        with self.assertRaises(PackError): load_pack(d)
        d=v2_example(); d['chronicle']['event_keys']=['chronicle.signature.changed']
        old=next(e for e in d['bank']['entries'] if e['key']=='chronicle.signature')
        old['key']='chronicle.signature.changed'
        self.assertNotEqual(expected,event_manifest(load_pack(d))['manifest_hash'])
        d=v2_example(); d['actors'][0]['intents'][0]['fact_slots']=['zone']
        # An invalid kind-specific slot set is rejected before bank validation.
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_V2_INTENT')
        d=v2_example(); intent=d['actors'][1]['intents'][1]
        intent.update(kind='strike',consequence='damage',damage=1,
                      fact_slots=['actor_name','target_name','damage'])
        old=next(e for e in d['bank']['entries'] if e['key']==intent['event_key'])
        old.update(fact_slots=intent['fact_slots'],variants=['{{actor_name}} {{target_name}} {{damage}}'],
                   fallback='{{actor_name}} {{target_name}} {{damage}}')
        self.assertNotEqual(expected,event_manifest(load_pack(d))['manifest_hash'])
        d=v2_example(); intent=d['actors'][0]['intents'][0]
        old=next(e for e in d['bank']['entries'] if e['key']=='actor.intent.cancelled')
        intent['cancel_event_key']='actor.intent.cancelled.custom'
        d['bank']['entries'].append({'key':intent['cancel_event_key'],'fact_slots':['actor_name','target_name'],
            'variants':['{{actor_name}} {{target_name}}'],'fallback':'{{actor_name}} {{target_name}}'})
        self.assertNotEqual(expected,event_manifest(load_pack(d))['manifest_hash'])

    def test_v2_rejects_v1_enemies_legend_fact_terminal_unknown_tag(self):
        for change in (
            lambda d:d.update(enemies=[]),
            lambda d:d.update(legend_meter={'max':5}),
            lambda d:d['terminals'][0].update(all=[{'kind':'fact_known','fact_id':'secret'}]),
            lambda d:d['materials'][0].update(tags=['acid']),
            lambda d:d['terminals'][0].update(all=[{'kind':'ability_used','ability_id':'wizard.fireball'}]),
            lambda d:d['terminals'][0].update(all=[{'kind':'route_label','route':'lure'}]),
            lambda d:d['terminals'][0].update(all=[{'kind':'event_key','key':'ability.wizard.fireball'}]),
        ):
            d=v2_example(); change(d)
            with self.assertRaises(PackError): load_pack(d)
        d=v2_example(); d['reaction_table'][8]['signal']='scent'
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_V2_RULE')

    def test_source_tag_and_rule_vocabulary_stays_in_sync(self):
        text=SPEC.read_text(encoding='utf-8')
        tag_line=re.search(r'Visible tags are finite and status-rendered:(.*)',text).group(1)
        tags=tuple(re.findall(r'`([^`]+)`',tag_line))
        rows=re.findall(r'^\| R(\d+) ([^|]+) \|',text,re.M)
        self.assertEqual(len(tags),14); self.assertEqual(tags,model.MATERIAL_TAGS)
        self.assertEqual(len(rows),12)
        self.assertEqual(tuple(name.strip().replace(' ','_') for _,name in rows),model.REACTION_RULES)

    def test_strict_types_unknown_fields_and_terminal_boundary(self):
        d=v2_example(); d['reaction_step_limit']=True
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_V2_RULE')
        d=v2_example(); d['class_actions'][0]['surprise']=1
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_SCHEMA')
        d=v2_example(); d['title']='bad\ud800'
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_SCHEMA')
        d=v2_example(); d['class_actions'][2]['effects'][0]['amount']=999
        with self.assertRaises(PackError) as cm: load_pack(d)
        self.assertEqual(cm.exception.code,'E_V2_ABILITY')
        self.assertIs(validate_pack(load_pack(v2_example())).__class__,model.V2Pack)

if __name__=='__main__': unittest.main()
