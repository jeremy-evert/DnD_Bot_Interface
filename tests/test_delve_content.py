import copy
import json
import re
import unittest
from collections import Counter
from pathlib import Path

from delve.pack import PackError, load_pack, load_engine_ready_pack, validate_pack
from delve.engine import Action, Engine
from delve.state import DelveState
from delve.render import RenderMemory, render_event

PACK_PATH = Path(__file__).parents[1] / 'delve' / 'content' / 'mossy_fast_slice.json'
DATA = json.loads(PACK_PATH.read_text(encoding='utf-8'))
OLD_OBJECTS = {'clapperless bell', 'stone compass', 'star chart', 'clay cup', 'silver leaf', 'offering bowl', 'brass nameplate'}
HOT_KEYS = {
    'room.enter', 'room.return', 'attack.hit', 'attack.miss', 'enemy.defeated',
    'intent.goblin.grab', 'intent.goblin.strike', 'intent.captain.guard', 'intent.captain.smash',
    'shove.success', 'shove.fail', 'brace.success', 'throw.leaf', 'throw.cup', 'hazard.trigger',
    'clue.reveal', 'clue.mira', 'clue.chart', 'clue.dome', 'item.get', 'item.use.bowl', 'get.blocked',
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


    def test_shipped_pack_is_engine_ready(self):
        self.assertEqual(load_engine_ready_pack(PACK_PATH).id, DATA['id'])

    def test_real_engine_route_wins_and_blind_vault_attack_costs_hp(self):
        pack = load_engine_ready_pack(PACK_PATH)

        def run(seed, actions):
            state = DelveState.new(pack, seed, 'fighter')
            engine = Engine(pack, state)
            memory = RenderMemory()
            transcript = []
            events = []
            for action in actions:
                emitted = engine.apply(action)
                for event in emitted:
                    self.assertIn(event.key, bank_map(), event.key)
                    self.assertTrue(set(bank_map()[event.key]['fact_slots']) <= set(event.fact_slots), event.key)
                    transcript.append(render_event(event, pack, seed, memory))
                    events.append(event)
            self.assertEqual(memory.problems, [])
            return state, events, transcript

        winning_actions = [Action('attack', 'goblin') for _ in range(6)]
        winning_actions += [
            Action('get', 'brass_ring_obj'),
            Action('move', direction='east'), Action('move', direction='south'),
            Action('use', 'brass_ring'), Action('look', 'mira'),
            Action('move', direction='north'), Action('look', 'collapsed_dome'),
            Action('move', direction='east'), Action('look', 'star_chart'),
            Action('move', direction='north'),
            Action('attack', 'captain'), Action('brace'), Action('attack', 'captain'),
            Action('shove', 'captain'), Action('attack', 'captain'),
        ]
        state, events, transcript = run(1, winning_actions)
        self.assertEqual(state.terminal, 'victory')
        self.assertEqual(set(state.known_clues), {'mira_route', 'chart_route', 'dome_route'})
        self.assertEqual(sum(event.key == 'fact.payoff' for event in events), 1)
        self.assertEqual(sum(event.key == 'enemy.defeated' and event.fact_slots.get('enemy_name') == 'Goblin' for event in events), 1)
        self.assertEqual(sum(event.key == 'enemy.defeated' and event.fact_slots.get('enemy_name') == 'Hobgoblin Captain' for event in events), 1)
        self.assertIn('hazard.trigger', [event.key for event in events])
        self.assertEqual(len(winning_actions), 21)
        print(f'Winning route actions used: {len(winning_actions)}')

        blind_actions = [Action('attack', 'goblin') for _ in range(6)] + [
            Action('move', direction='east'), Action('move', direction='east'),
            Action('move', direction='north'), Action('attack', 'captain'),
            Action('attack', 'captain'),
        ]
        blind, blind_events, _ = run(1, blind_actions)
        self.assertFalse(blind.known_facts)
        self.assertTrue(blind.player['hp'] < blind.player['max_hp'] or blind.terminal == 'dead')

    def test_scripted_event_bank_coverage_renders_variants_without_problems(self):
        pack = load_engine_ready_pack(PACK_PATH)
        bank = bank_map()
        all_events = []
        def collect(state, engine, actions):
            out = []
            for action in actions:
                out.extend(engine.apply(action))
                if state.terminal != 'playing': break
            all_events.extend(out)
            return out

        # A complete clue-driven win also contributes terminal and hazard paths.
        state = DelveState.new(pack, 1, 'fighter'); engine = Engine(pack,state)
        win_actions = [Action('attack','goblin') for _ in range(6)] + [
            Action('get','brass_ring_obj'), Action('move',direction='east'),
            Action('move',direction='south'), Action('use','brass_ring'), Action('look','mira'),
            Action('move',direction='north'), Action('look','collapsed_dome'),
            Action('move',direction='east'), Action('look','star_chart'), Action('move',direction='north'),
            Action('attack','captain'), Action('brace'), Action('attack','captain'),
            Action('shove','captain'), Action('attack','captain'),
        ]
        collect(state,engine,win_actions)
        self.assertEqual(state.terminal,'victory')

        # Death by each enemy, including all three death slots supplied by Engine.
        for room_id, enemy_id in (('mossy_entry','goblin'), ('hollow_vault','captain')):
            state = DelveState.new(pack, 1, 'wizard'); state.room_id = room_id
            engine = Engine(pack,state)
            collect(state,engine,[Action('attack',enemy_id) for _ in range(8)])
            self.assertEqual(state.terminal, 'dead')

        # A normal four-step patrol route applies the fourth-step damage after its line.
        state = DelveState.new(pack, 1, 'fighter'); state.room_id = 'collapsed_observatory'
        state.clocks['patrol'] = 3; hp_before = state.player['hp']; engine = Engine(pack,state)
        events = collect(state,engine,[Action('move',direction='east')])
        keys = [event.key for event in events]
        self.assertIn('clock.threshold.patrol.4', keys)
        self.assertEqual(state.player['hp'], hp_before - 4)

        # Collect reachable throw and bowl events from regular room/inventory play.
        state = DelveState.new(pack, 1, 'fighter'); engine = Engine(pack,state)
        for _ in range(6): engine.apply(Action('attack','goblin'))
        for action in (Action('move',direction='east'), Action('move',direction='south'),
                       Action('get','silver_leaf_obj'), Action('move',direction='north'),
                       Action('move',direction='east'), Action('move',direction='north'),
                       Action('throw','silver_leaf')):
            all_events.extend(engine.apply(action))
        state = DelveState.new(pack, 1, 'fighter'); engine = Engine(pack,state)
        state.room_id = 'collapsed_observatory'; state.player['hp'] = 10
        all_events.extend(engine.apply(Action('get','offering_bowl')))
        all_events.extend(engine.apply(Action('use','offering_bowl_item')))

        rendered = RenderMemory()
        probe_entries = []
        for entry in pack.bank:
            probe_entries.append({'key':entry.key,'fact_slots':list(entry.fact_slots),
                                  'variants':list(entry.variants),
                                  'fallback':'__FALLBACK_ONLY__ ' + ' '.join('{{'+slot+'}}' for slot in entry.fact_slots)})
        probe_pack = {'bank':{'entries':probe_entries}}
        self.assertTrue(all_events)
        for event in all_events:
            self.assertIn(event.key, bank, event.key)
            self.assertTrue(set(bank[event.key]['fact_slots']) <= set(event.fact_slots), event.key)
            line = render_event(event, probe_pack, 1, rendered)
            self.assertFalse(line.startswith('__FALLBACK_ONLY__'), event.key)
        self.assertEqual(rendered.problems, [])

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
        self.assertEqual(mira['reader']['event_key'], 'object.read')
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
        items = {item['id']: item for item in DATA['items']}
        self.assertEqual(items['clay_cup']['throw_tags'], ['interrupt_smash'])
        self.assertEqual(items['silver_leaf']['throw_tags'], ['interrupt_guard'])
        self.assertEqual(items['clay_cup']['reader']['event_key'], 'throw.cup')
        self.assertEqual(items['silver_leaf']['reader']['event_key'], 'throw.leaf')
        self.assertEqual(bank_map()['throw.cup']['fact_slots'], ['item_name'])
        self.assertEqual(bank_map()['throw.leaf']['fact_slots'], ['item_name'])
        expected_look_keys = {
            'brass_ring_obj':'object.ring', 'collapsed_dome':'object.dome',
            'clapperless_bell':'object.bell', 'stone_compass':'object.compass',
            'star_chart':'object.chart', 'clay_cup_obj':'object.cup',
            'silver_leaf_obj':'object.leaf', 'offering_bowl':'object.bowl',
            'brass_nameplate':'object.nameplate',
        }
        for object_id, key in expected_look_keys.items():
            self.assertEqual(objects[object_id]['reader']['event_key'], key)
        bank = bank_map()
        for key in ('get.blocked', 'get.not_takeable', 'use.nothing'):
            self.assertGreaterEqual(len(bank[key]['variants']), 4, key)
            self.assertTrue(bank[key]['fallback'].strip())

    def test_pickups_are_reachable_before_combat_and_bowl_is_consumable(self):
        by_room = {room['id']: room for room in DATA['rooms']}
        room_for = {obj['id']: room['id'] for room in DATA['rooms'] for obj in room['objects']}
        self.assertEqual(room_for['clay_cup_obj'], 'chart_chamber')
        self.assertEqual(room_for['silver_leaf_obj'], 'mira_gallery')
        self.assertEqual(room_for['offering_bowl'], 'collapsed_observatory')
        for room_id in ('chart_chamber', 'mira_gallery', 'collapsed_observatory'):
            self.assertFalse(any(e['room_id'] == room_id for e in DATA['enemies']))
        for object_id, key in [('clay_cup_obj','object.cup'), ('silver_leaf_obj','object.leaf'),
                               ('offering_bowl','object.bowl')]:
            obj = next(o for r in DATA['rooms'] for o in r['objects'] if o['id'] == object_id)
            self.assertEqual(obj['reader']['event_key'], key)
        bowl = next(i for i in DATA['items'] if i['id'] == 'offering_bowl_item')
        self.assertTrue(bowl['consumed_on_use'])
        self.assertEqual(bowl['reader']['effects'], [{'type':'heal','target':'player','amount':8}])
        self.assertNotIn('when_room_id', bowl['reader'])

        pack = load_engine_ready_pack(PACK_PATH)
        state = DelveState.new(pack, 1, 'fighter'); engine = Engine(pack, state)
        state.room_id = 'collapsed_observatory'
        state.player['hp'] = 10
        engine.apply(Action('get','offering_bowl'))
        events = engine.apply(Action('use','offering_bowl_item'))
        self.assertEqual(state.player['hp'], 18)
        self.assertIn('item.use.bowl', [e.key for e in events])
        self.assertNotIn('offering_bowl_item', state.inventory)
        again = engine.apply(Action('use','offering_bowl_item'))
        self.assertEqual(state.player['hp'], 18)
        self.assertNotIn('item.use.bowl', [e.key for e in again])

    def test_leaf_interrupts_guard_and_cup_interrupts_smash_in_play(self):
        pack = load_engine_ready_pack(PACK_PATH)
        def clear_goblin(state, engine):
            for _ in range(6): engine.apply(Action('attack','goblin'))
        # The cycle starts at guard. Taking the leaf to the vault strips that guard.
        state = DelveState.new(pack, 1, 'fighter'); engine = Engine(pack,state); clear_goblin(state,engine)
        engine.apply(Action('move',direction='east')); engine.apply(Action('move',direction='south'))
        engine.apply(Action('get','silver_leaf_obj')); engine.apply(Action('move',direction='north'))
        engine.apply(Action('move',direction='east')); engine.apply(Action('move',direction='north'))
        events = engine.apply(Action('throw','silver_leaf'))
        self.assertIn('throw.leaf', [e.key for e in events])
        self.assertIn('intent.cancelled', [e.key for e in events])
        self.assertEqual(state.enemies['captain']['current_intent_id'], 'smash')
        self.assertEqual(state.inventory, [])

        # A cup in the chart chamber is available before entering the Captain's room.
        state = DelveState.new(pack, 1, 'fighter'); engine = Engine(pack,state); clear_goblin(state,engine)
        engine.apply(Action('move',direction='east')); engine.apply(Action('move',direction='east'))
        engine.apply(Action('get','clay_cup_obj')); engine.apply(Action('move',direction='north'))
        engine.apply(Action('brace'))  # guard resolves harmlessly; smash is now declared
        self.assertEqual(state.enemies['captain']['current_intent_id'], 'smash')
        events = engine.apply(Action('throw','clay_cup'))
        self.assertIn('throw.cup', [e.key for e in events])
        self.assertIn('intent.cancelled', [e.key for e in events])
        self.assertEqual(state.enemies['captain']['current_intent_id'], 'guard')

    def test_patrol_clock_has_direct_and_full_sweep_routes(self):
        patrol = next(c for c in DATA['clocks'] if c['id'] == 'patrol')
        self.assertEqual({t['at'] for t in patrol['thresholds']}, {2, 4})
        self.assertEqual(patrol['tick_sources'], [{'source': 'move', 'amount': 1}, {'source': 'retreat', 'amount': 1}])
        alert, caught = patrol['thresholds']
        self.assertEqual(alert['effects'], [{'type': 'set_flag', 'flag_id': 'patrol_alert', 'value': True}])
        self.assertEqual(caught['effects'], [{'type': 'damage', 'target': 'player', 'amount': 4}])
        self.assertIn('clock.threshold.patrol.4', bank_map())
        self.assertIn('clock.threshold.patrol.2', bank_map())
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
                has_purpose = obj['id'] in clue_sources or 'item_id' in obj or any(e['type'] in {'reveal_clue', 'set_flag'} for e in effects)
                self.assertTrue(effects or has_purpose, obj['id'])


if __name__ == '__main__':
    unittest.main()
