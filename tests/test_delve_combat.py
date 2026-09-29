import copy
import json
import random
import re
import unittest
from pathlib import Path

from delve.engine import Action, Engine
from delve.pack import load_pack
from delve.state import DelveState

SPEC = Path(__file__).parents[1] / 'docs' / 'DELVE_M1_SPEC.md'
EXAMPLE = json.loads(re.search(r'### Complete valid example\s*```json\s*(.*?)\s*```', SPEC.read_text(), re.S).group(1))


class ScriptedRandom(random.Random):
    def __init__(self, values):
        super().__init__(0)
        self.values = list(values)

    def randint(self, a, b):
        value = self.values.pop(0)
        assert a <= value <= b, (a, b, value)
        return value


def assert_telegraph_invariant(testcase, event_log):
    """Every enemy hit must be preceded by a still-current declaration."""
    declared = {}
    for event in event_log:
        key = event['key']
        if key.startswith('intent.'):
            declared[event['fact_slots'].get('enemy_name')] = key
        if key == 'enemy.hit':
            name = event['fact_slots'].get('enemy_name')
            testcase.assertIn(name, declared, f'{name} dealt damage without a prior intent declaration')
            testcase.assertTrue(declared[name], f'{name} dealt damage after its declaration was already resolved')
            declared[name] = False


def combat_pack():
    data = copy.deepcopy(EXAMPLE)
    entries = data['bank']['entries']
    keys = {entry['key'] for entry in entries}
    for key, slots in [
        ('attack.hit', ['enemy_name', 'damage']), ('attack.miss', ['margin']),
        ('brace.success', []), ('brace.wasted', []), ('enemy.hit', ['enemy_name', 'damage']),
        ('enemy.miss', ['enemy_name']), ('retreat.blocked', []), ('combat.not_yet', []),
        ('get.blocked', ['enemy_name']), ('get.not_takeable', ['object_name']),
        ('use.nothing', []), ('item.get', ['item_name']),
    ]:
        if key not in keys:
            value = ' '.join('{{' + slot + '}}' for slot in slots) or 'x'
            entries.append({'key': key, 'fact_slots': slots, 'variants': [value], 'fallback': value})
    enemy = data['enemies'][0]
    kinds = [('smash', 3), ('guard', 0), ('strike', 1), ('rush', 2), ('grab', 4)]
    enemy['intent_cycle'] = [name for name, _ in kinds]
    enemy['intents'] = []
    for name, amount in kinds:
        key = f'intent.captain.{name}'
        if key not in keys:
            entries.append({'key': key, 'fact_slots': ['enemy_name'], 'variants': ['{{enemy_name}}'], 'fallback': '{{enemy_name}}'})
            keys.add(key)
        enemy['intents'].append({
            'id': name, 'type': name, 'telegraph_key': key, 'target_zone': 'doorway',
            'effects': [{'type': 'damage', 'target': 'player', 'amount': amount}], 'counters': [],
        })
    data['items'].append({'id': 'vault_token', 'name': 'vault token', 'reader': {
        'on': 'use', 'event_key': 'use.nothing', 'effects': [],
    }})
    data['rooms'][1]['objects'].append({
        'id': 'vault_token_obj', 'name': 'vault token', 'zone': 'near', 'item_id': 'vault_token',
        'reader': {'on': 'look', 'event_key': 'object.read', 'effects': []},
    })
    return load_pack(data)


class CombatTests(unittest.TestCase):
    def setUp(self):
        self.pack = combat_pack()
        self.s = DelveState.new(self.pack, 4, 'fighter')
        self.e = Engine(self.pack, self.s)
        self.s.room_id = 'vault'
        self.s.player['zone'] = 'doorway'

    def scripted(self, *rolls):
        self.s.rng = ScriptedRandom(rolls)

    def act(self, verb, target=None, direction=None):
        return self.e.apply(Action(verb, target, direction))

    def declare(self, kind=None):
        enemy = self.e._living_enemy()
        if kind:
            self.s.enemies[enemy.id]['current_intent_id'] = kind
        intent = self.e._current_intent(enemy)
        self.s.event_log.append(self.e._event(intent.telegraph_key, {'enemy_name': enemy.name}, typ='enemy_intent').to_dict())
        return enemy, intent

    def test_attack_exact_draws_nat20_nat1_and_guard_ac(self):
        self.declare('strike')
        draws = self.s.rng_draws
        self.scripted(10, 4, 1, 1)
        self.assertEqual(self.act('attack')[0].key, 'attack.hit')
        self.assertEqual(self.s.rng_draws - draws, 4)  # Two attack rolls and two intent rolls.
        self.assertEqual(self.s.event_log[-3]['numbers']['damage'], 7)
        round_keys = [event['key'] for event in self.s.event_log]
        self.assertLess(round_keys.index('attack.hit'), round_keys.index('enemy.miss'))
        self.declare('guard')
        draws = self.s.rng_draws
        self.scripted(10, 1, 1, 1)
        self.assertEqual(self.act('attack')[0].key, 'attack.miss')
        self.assertEqual(self.s.rng_draws - draws, 4)
        self.declare('strike'); self.scripted(20, 1, 1, 1)
        self.assertEqual(self.act('attack')[0].key, 'attack.hit')
        self.declare('strike'); self.scripted(1, 1, 20, 1)
        self.assertEqual(self.act('attack')[0].key, 'attack.miss')
        self.assertEqual(self.s.event_log[-3]['numbers']['margin'], -8)

    def test_intent_brace_table_effect_damage_and_draws(self):
        enemy = self.e._living_enemy()
        for kind, counter, expected in [('strike', 'halve', 3), ('smash', 'negate', 0), ('grab', 'resist', 0), ('guard', None, 6)]:
            self.s.player['hp'] = 24
            self.s.enemies[enemy.id]['current_intent_id'] = kind
            draws = self.s.rng_draws
            self.scripted(20, 4)
            events = []
            self.e._resolve_intent(enemy, counter, events)
            self.assertEqual(self.s.rng_draws - draws, 2)
            self.assertEqual(self.s.player['hp'], 24 - expected)
        # Guard is explicitly wasted; the enemy still resolves its intent.
        self.s.enemies[enemy.id]['current_intent_id'] = 'guard'
        self.declare('guard'); self.scripted(20, 4)
        self.assertEqual(self.act('brace')[0].key, 'brace.wasted')
        # Wrong implementation guard: brace must change incoming strike damage.
        self.s.player['hp'] = 24; self.s.enemies[enemy.id]['current_intent_id'] = 'strike'
        self.declare('strike'); self.scripted(20, 4)
        self.act('brace')
        self.assertEqual(self.s.player['hp'], 21)
        # Wrong implementation guard: a cancelled rush must consume no dice.
        self.s.enemies[enemy.id]['current_intent_id'] = 'rush'
        self.declare('rush'); before = self.s.rng_draws; self.scripted()
        events = self.act('brace')
        self.assertEqual(self.s.rng_draws - before, 0)
        self.assertNotIn('enemy.hit', [event.key for event in events])
        # A non-damaging intent's state effects apply even when its attack roll misses.
        guard = next(i for i in enemy.intents if i.id == 'guard')
        object.__setattr__(guard, 'effects', (type('Effect', (), {'type': 'set_flag', 'flag_id': 'grabbed', 'value': True})(),))
        self.s.enemies[enemy.id]['current_intent_id'] = 'guard'
        self.scripted(1, 1)
        self.e._resolve_intent(enemy, None, [])
        self.assertIn('grabbed', self.s.flags)

    def test_non_damaging_grab_applies_move_zone_and_flag_on_hit(self):
        # Per Amendment 3 point 4, a grab with no damage effect applies its effects on resolution.
        enemy = self.e._living_enemy()
        intent = next(i for i in enemy.intents if i.id == 'grab')
        self.s.enemies[enemy.id]['current_intent_id'] = 'grab'
        effects = (
            type('Effect', (), {'type': 'move_zone', 'actor': 'player', 'zone': 'far'})(),
            type('Effect', (), {'type': 'set_flag', 'flag_id': 'grabbed', 'value': True})(),
        )
        object.__setattr__(intent, 'effects', effects)
        draws = self.s.rng_draws; self.scripted(20, 2)
        self.e._resolve_intent(enemy, None, [])
        self.assertEqual(self.s.rng_draws - draws, 2)
        self.assertEqual(self.s.player['zone'], 'far')
        self.assertIn('grabbed', self.s.flags)

    def test_five_hundred_seeded_action_sequences_hold_telegraph_invariant(self):
        for seed in (3, 17, 2026, 9107, 44119):
            chooser = random.Random(seed)
            for _ in range(100):
                state = DelveState.new(self.pack, seed, 'fighter')
                state.room_id = 'vault'; state.player['zone'] = 'doorway'
                engine = Engine(self.pack, state)
                enemy = engine._living_enemy(); intent = engine._current_intent(enemy)
                state.event_log.append(engine._event(intent.telegraph_key, {'enemy_name': enemy.name}, typ='enemy_intent').to_dict())
                actions = ['attack', 'brace', 'get', 'use', 'retreat', 'move', 'help']
                for _ in range(12):
                    try:
                        engine.apply(Action(chooser.choice(actions), 'captain', chooser.choice(('west', 'north'))))
                    except Exception as exc:
                        self.fail(f'seed {seed}: action sequence raised {exc!r}')
                    assert_telegraph_invariant(self, state.event_log)

    def test_hand_injected_undeclared_enemy_hit_is_caught(self):
        fake = [{'key': 'enemy.hit', 'fact_slots': {'enemy_name': 'Hobgoblin Captain'}}]
        with self.assertRaises(AssertionError):
            assert_telegraph_invariant(self, fake)

    def test_death_attribution_uses_killing_intent_and_terminal_slot(self):
        self.s.player['hp'] = 1
        self.declare('smash'); self.scripted(20, 8)
        events = self.act('brace')
        # Smash is negated by brace, so make the follow-up strike lethal instead.
        self.assertNotEqual(self.s.terminal, 'dead')
        self.declare('strike'); self.s.player['hp'] = 1; self.scripted(20, 8, 20, 1)
        events = self.act('attack')
        death = next(e for e in events if e.key == 'terminal.death')
        self.assertEqual(self.s.terminal, 'dead')
        self.assertEqual(death.fact_slots['cause'], 'Hobgoblin Captain strike')
        self.assertIn('__player_hp_zero', self.s.flags)

    def test_victory_predicate_both_orders(self):
        # Enemy dies before the fact becomes known.
        self.declare('guard'); self.s.enemies['captain']['hp'] = 1
        self.scripted(20, 1, 1, 1)
        self.act('attack')
        self.assertEqual(self.s.enemies['captain']['hp'], 0)
        self.assertEqual(self.s.terminal, 'playing')
        self.s.known_facts.append('captain_route')
        self.act('help')
        self.assertEqual(self.s.terminal, 'victory')
        # Fact known before the enemy dies.
        other = self.__class__(); other.setUp()
        other.s.known_facts.append('captain_route'); other.declare('strike')
        other.s.enemies['captain']['hp'] = 1; other.scripted(20, 1, 1, 1)
        events = other.act('attack')
        self.assertEqual(other.s.terminal, 'victory')
        self.assertIn('terminal.victory', [e.key for e in events])

    def test_enemy_death_clears_intent_and_frees_move_and_get(self):
        self.declare('guard'); self.s.enemies['captain']['hp'] = 1
        self.scripted(20, 1, 1, 1)
        self.act('attack')
        self.assertIsNone(self.s.enemies['captain']['current_intent_id'])
        # Drop a takeable object into the now unoccupied room to cover get.
        self.assertEqual(self.act('get', 'vault_token_obj')[0].key, 'item.get')
        self.assertEqual(self.act('move', direction='west')[0].key, 'room.return')

    def test_retreat_only_doorway_ungated_clock_and_preserves_enemy_intent(self):
        self.declare('strike')
        before_draws = self.s.rng_draws
        events = self.act('retreat', direction='west')
        self.assertEqual(self.s.room_id, 'entry')
        self.assertEqual(self.s.clocks['patrol'], 1)
        self.assertEqual(self.s.rng_draws, before_draws)
        self.assertNotIn('enemy.hit', [event.key for event in events])
        self.assertEqual(self.s.enemies['captain']['current_intent_id'], 'strike')
        self.s.room_id = 'vault'; self.s.player['zone'] = 'near'
        self.assertEqual(self.act('retreat', direction='west')[0].key, 'retreat.blocked')
        self.s.player['zone'] = 'doorway'; self.s.enemies['captain']['current_intent_id'] = 'grab'
        self.assertEqual(self.act('retreat', direction='west')[0].key, 'retreat.blocked')

    def test_invalid_action_snapshot_except_log_and_turn_and_zero_draws(self):
        before = self.s.snapshot(); self.scripted()
        event = self.act('retreat', direction='north')[0]
        after = self.s.snapshot()
        for snap in (before, after):
            snap.pop('event_log', None); snap.pop('turn', None); snap.pop('canonical_state_hash', None)
        self.assertEqual(before, after)
        self.assertEqual(event.key, 'retreat.blocked')
        self.assertEqual(self.s.rng_draws, 0)

    def test_deterministic_replay_and_global_random_untouched(self):
        actions = [Action('attack'), Action('brace'), Action('retreat', direction='west')]
        global_before = random.getstate()
        def replay():
            state = DelveState.new(self.pack, 987, 'fighter'); state.room_id = 'vault'; state.player['zone'] = 'doorway'
            engine = Engine(self.pack, state)
            intent = engine._current_intent(engine._living_enemy())
            state.event_log.append(engine._event(intent.telegraph_key, {'enemy_name': 'Hobgoblin Captain'}, typ='enemy_intent').to_dict())
            for action in actions: engine.apply(action)
            snap = state.snapshot()
            return snap['event_log'], snap['canonical_state_hash']
        self.assertEqual(replay(), replay())
        self.assertEqual(random.getstate(), global_before)


if __name__ == '__main__':
    unittest.main()
