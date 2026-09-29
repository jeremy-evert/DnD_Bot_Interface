import copy
import json
import re
import tempfile
import unittest
from pathlib import Path
from dataclasses import FrozenInstanceError

from delve import PackError, load_pack, validate_pack

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

# Exercise semantic validation independently of the strict public loader.
def load_unvalidated(d):
    from delve.pack import _parse
    return _parse(d)

if __name__=='__main__': unittest.main()
