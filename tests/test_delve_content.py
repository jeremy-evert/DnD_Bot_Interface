import copy
import json
import re
import unittest
from collections import Counter
from pathlib import Path

from delve.pack import PackError, load_pack, validate_pack

PACK_PATH = Path(__file__).parents[1] / 'delve' / 'content' / 'mossy_fast_slice.json'
DATA = json.loads(PACK_PATH.read_text(encoding='utf-8'))
OLD_OBJECTS = {'clapperless bell', 'stone compass', 'star chart', 'clay cup', 'silver leaf', 'offering bowl', 'brass nameplate'}
HOT_KEYS = {'room.enter', 'attack.hit', 'attack.miss', 'enemy.intent', 'intent.goblin.grab', 'intent.goblin.strike', 'intent.captain.guard', 'intent.captain.smash'}
# D&D is a vocabulary label in authored feedback; Ada is the hero slot.
PROPER_ALLOWLIST = {'HP', 'D&D', 'Ada', 'Mira'}


def bank_map(data=DATA):
    return {entry['key']: entry for entry in data['bank']['entries']}


def referenced_keys(data):
    out = {r['description_key'] for r in data['rooms']}
    for room in data['rooms']:
        for obj in room['objects']:
            if 'reader' in obj:
                out.add(obj['reader']['event_key'])
    for item in data['items']:
        out.add(item['reader']['event_key'])
    for enemy in data['enemies']:
        out.update(i['telegraph_key'] for i in enemy['intents'])
    for hazard in data['hazards']:
        out.add(hazard['event_key'])
    for clue in data['truth']['clues']:
        out.add(clue['event_key'])
    for terminal in data['terminals']:
        out.add(terminal['event_key'])
        if 'retry_hint_key' in terminal:
            out.add(terminal['retry_hint_key'])
    return out


class DelveContentTests(unittest.TestCase):
    def test_pack_loads_and_validates(self):
        pack = load_pack(PACK_PATH)
        self.assertEqual(validate_pack(pack), pack)

    def test_exact_five_named_rooms(self):
        self.assertEqual({r['id'] for r in DATA['rooms']}, {
            'mossy_entry', 'collapsed_observatory', 'chart_chamber', 'mira_gallery', 'hollow_vault'
        })
        self.assertEqual(len(DATA['rooms']), 5)

    def test_captain_route_has_three_independent_clues_and_each_is_required(self):
        fact = next(f for f in DATA['truth']['facts'] if f['id'] == 'captain_route')
        clues = {c['id']: c for c in DATA['truth']['clues']}
        selected = [clues[c] for c in fact['clue_ids']]
        self.assertEqual(len(selected), 3)
        self.assertEqual(len({c['source_id'] for c in selected}), 3)
        self.assertEqual({c['room_id'] for c in selected}, {'mira_gallery', 'chart_chamber', 'collapsed_observatory'})
        self.assertEqual({c['source_id'] for c in selected}, {'mira', 'star_chart', 'collapsed_dome'})
        mira = next(o for r in DATA['rooms'] for o in r['objects'] if o['id'] == 'mira')
        self.assertEqual(mira['reader']['on'], 'look')
        self.assertEqual(mira['reader']['when_flag_id'], 'ring_given')
        ring = next(i for i in DATA['items'] if i['id'] == 'brass_ring')
        self.assertEqual(ring['reader']['when_room_id'], 'mira_gallery')
        self.assertEqual(ring['reader']['effects'], [{'type': 'set_flag', 'flag_id': 'ring_given', 'value': True}])
        self.assertIn('Mira', bank_map()['room.gallery']['variants'][0])
        self.assertIn('wants it', bank_map()['room.gallery']['variants'][0])
        for clue in selected:
            changed = copy.deepcopy(DATA)
            changed['truth']['facts'][0]['clue_ids'].remove(clue['id'])
            changed['truth']['clues'] = [c for c in changed['truth']['clues'] if c['id'] != clue['id']]
            with self.assertRaises(PackError) as cm:
                load_pack(changed)
            self.assertEqual(cm.exception.code, 'E_FACT_CLUE_COUNT')

    def test_every_legacy_object_has_a_reader_or_declared_atmosphere_role(self):
        seen = {}
        for room in DATA['rooms']:
            for obj in room['objects']:
                seen[obj['name']] = 'reader' if 'reader' in obj else f"atmosphere:{obj.get('atmosphere_id')}"
        self.assertTrue(OLD_OBJECTS <= seen.keys(), OLD_OBJECTS - seen.keys())
        self.assertTrue(all(seen[name] == 'reader' for name in OLD_OBJECTS), seen)

    def test_bank_coverage_variants_slots_digits_and_names(self):
        bank = bank_map()
        self.assertTrue(referenced_keys(DATA) <= bank.keys(), referenced_keys(DATA) - bank.keys())
        for key in HOT_KEYS:
            self.assertIn(key, bank)
            self.assertGreaterEqual(len(set(bank[key]['variants'])), 4, key)
        allowed_names = {r['title'] for r in DATA['rooms']} | {e['name'] for e in DATA['enemies']}
        allowed_names |= {o['name'] for r in DATA['rooms'] for o in r['objects']}
        allowed_names |= {i['name'] for i in DATA['items']} | {'Mira', 'Ada'}
        allowed_words = {w for name in allowed_names for w in re.findall(r"[A-Z][a-zA-Z']*", name)} | PROPER_ALLOWLIST
        for entry in DATA['bank']['entries']:
            self.assertTrue(entry['fallback'].strip(), entry['key'])
            self.assertEqual(len(entry['variants']), len(set(entry['variants'])), entry['key'])
            declared = set(entry['fact_slots'])
            for text in [*entry['variants'], entry['fallback']]:
                self.assertEqual(set(re.findall(r'{{([^{}]+)}}', text)), declared, (entry['key'], text))
                self.assertIsNone(re.search(r'\d', text), (entry['key'], text))
                cleaned = re.sub(r'{{[^{}]+}}', '', text)
                for sentence in re.split(r'(?<=[.!?])\s+', cleaned):
                    words = re.findall(r"\b[A-Z][a-zA-Z']*\b", sentence)
                    for word in words[1:]:
                        self.assertIn(word, allowed_words, (entry['key'], word, text))

    def test_vault_reachable_without_mira_and_ring_not_only_progress(self):
        graph = {r['id']: {e['to_room_id'] for e in r['exits']} for r in DATA['rooms']}
        seen = {DATA['start_room_id']}
        todo = list(seen)
        while todo:
            for nxt in graph[todo.pop()] - seen:
                seen.add(nxt)
                todo.append(nxt)
        self.assertIn('hollow_vault', seen)
        clue_rooms = {c['room_id'] for c in DATA['truth']['clues']}
        self.assertTrue(clue_rooms - {'mira_gallery'})
        self.assertTrue(any(c['room_id'] == 'chart_chamber' for c in DATA['truth']['clues']))

    def test_reader_is_not_empty_without_a_flag_or_clue_purpose(self):
        clue_sources = {c['source_id'] for c in DATA['truth']['clues']}
        for room in DATA['rooms']:
            for obj in room['objects']:
                reader = obj.get('reader')
                if reader is None:
                    continue
                effects = reader['effects']
                has_purpose = obj['id'] in clue_sources or any(e['type'] in {'reveal_clue', 'set_flag'} for e in effects)
                self.assertTrue(effects or has_purpose, obj['id'])


if __name__ == '__main__':
    unittest.main()
