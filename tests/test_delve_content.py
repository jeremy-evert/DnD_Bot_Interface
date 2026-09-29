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
HOT_KEYS = {
    'room.enter', 'room.return', 'attack.hit', 'attack.miss', 'enemy.intent',
    'intent.goblin.grab', 'intent.goblin.strike', 'intent.captain.guard', 'intent.captain.smash',
    'shove.success', 'shove.fail', 'brace.success', 'throw.interrupt', 'hazard.trigger',
    'clue.reveal', 'clue.mira', 'clue.chart', 'clue.dome', 'item.get', 'item.use', 'get.blocked',
}
# D&D is a vocabulary label in authored feedback; Ada is the hero slot.
PROPER_ALLOWLIST = {'HP', 'D&D', 'Ada', 'Mira', 'The', 'Your', 'A', 'Both', 'One', 'Back', 'Fresh'}


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

    def test_pickup_links_and_banks(self):
        objects = {o['id']: o for r in DATA['rooms'] for o in r['objects']}
        self.assertEqual(objects['brass_ring_obj']['item_id'], 'brass_ring')
        self.assertEqual(objects['clay_cup_obj']['item_id'], 'clay_cup')
        self.assertEqual(objects['silver_leaf_obj']['item_id'], 'silver_leaf')
        bank = bank_map()
        for key in ('get.blocked', 'get.not_takeable', 'use.nothing'):
            self.assertGreaterEqual(len(bank[key]['variants']), 4, key)
            self.assertTrue(bank[key]['fallback'].strip())

    def test_patrol_clock_has_direct_and_full_sweep_routes(self):
        patrol = next(c for c in DATA['clocks'] if c['id'] == 'patrol')
        self.assertEqual({t['at'] for t in patrol['thresholds']}, {2, 4})
        self.assertEqual(patrol['tick_sources'], [{'source': 'move', 'amount': 1}, {'source': 'retreat', 'amount': 1}])
        alert, caught = patrol['thresholds']
        self.assertEqual(alert['effects'], [{'type': 'set_flag', 'flag_id': 'patrol_alert', 'value': True}])
        self.assertEqual(caught['effects'], [{'type': 'damage', 'target': 'player', 'amount': 4}])
        self.assertIn('clock.caught', bank_map())
        graph = {r['id']: {e['to_room_id'] for e in r['exits']} for r in DATA['rooms']}
        direct = ['mossy_entry', 'collapsed_observatory', 'chart_chamber', 'hollow_vault']
        self.assertTrue(all(b in graph[a] for a, b in zip(direct, direct[1:])))
        min_moves = len(direct) - 1
        self.assertLess(min_moves, 4)
        sweep = ['mossy_entry', 'collapsed_observatory', 'chart_chamber', 'mira_gallery', 'hollow_vault']
        self.assertTrue(all(b in graph[a] for a, b in zip(sweep, sweep[1:])))
        self.assertGreaterEqual(len(sweep) - 1, 4)

    def test_every_set_flag_is_read_or_documented_message_only(self):
        set_flags = set()
        read_flags = set()
        for room in DATA['rooms']:
            for obj in room['objects']:
                reader = obj.get('reader', {})
                if 'when_flag_id' in reader:
                    read_flags.add(reader['when_flag_id'])
                set_flags.update(e['flag_id'] for e in reader.get('effects', []) if e['type'] == 'set_flag')
        for item in DATA['items']:
            reader = item['reader']
            if 'when_flag_id' in reader:
                read_flags.add(reader['when_flag_id'])
            set_flags.update(e['flag_id'] for e in reader['effects'] if e['type'] == 'set_flag')
        for clock in DATA['clocks']:
            for threshold in clock['thresholds']:
                set_flags.update(e['flag_id'] for e in threshold['effects'] if e['type'] == 'set_flag')
        for fact in DATA['truth']['facts']:
            set_flags.update(e['flag_id'] for e in fact['payoff_effects'] if e['type'] == 'set_flag')
        for hazard in DATA['hazards']:
            read_flags.add(hazard['trigger']['requires_flag_id'])
        for room in DATA['rooms']:
            for exit_ in room['exits']:
                if 'gate' in exit_:
                    read_flags.add(exit_['gate']['flag_id'])
        for terminal in DATA['terminals']:
            read_flags.update(p['flag_id'] for p in terminal['all'] if p['kind'] == 'flag_set')
        notes = DATA.get('meta', {}).get('notes', '')
        message_only = {flag for flag in set_flags if flag in notes}
        self.assertEqual(set_flags - read_flags - message_only, set())

    def test_bank_lint_banned_tokens_and_voice_coverage(self):
        bank = bank_map()
        neutral_room_lines = set(bank['room.enter']['variants'])
        for key in HOT_KEYS:
            self.assertGreaterEqual(len(bank[key]['variants']), 5, key)
        for entry in DATA['bank']['entries']:
            for text in [*entry['variants'], entry['fallback']]:
                self.assertNotIn('hammer', text.lower(), (entry['key'], text))
                self.assertIsNone(re.search(r'\d', text), (entry['key'], text))
                cleaned = re.sub(r'{{[^{}]+}}', '', text)
                self.assertNotIn('{{', cleaned, (entry['key'], text))
                self.assertNotIn('}}', cleaned, (entry['key'], text))
                if 'You enter' in text:
                    self.assertEqual(entry['key'], 'room.enter')
                    self.assertIn(text, neutral_room_lines)
        for cause in ('damage', 'the patrol', 'the Captain'):
            death = [v for v in bank['terminal.death']['variants'] if '{{cause}}' in v]
            self.assertGreaterEqual(len(death), 3, cause)

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
