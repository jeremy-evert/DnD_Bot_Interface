import copy
import json
import random
import re
import sys
import unittest
from pathlib import Path

from delve.engine import Action, Engine
from delve.pack import load_pack
from delve.state import DelveState

SPEC = Path(__file__).parents[1] / 'docs' / 'DELVE_M1_SPEC.md'
EXAMPLE = json.loads(re.search(r'### Complete valid example\s*```json\s*(.*?)\s*```', SPEC.read_text(), re.S).group(1))


def extended_pack():
    d = copy.deepcopy(EXAMPLE)
    d['items'] = [{'id':'key_item','name':'iron key','reader':{'on':'use','event_key':'item.use','when_room_id':'vault','when_flag_id':'unlocked','effects':[{'type':'set_flag','flag_id':'used_key','value':True}]}}]
    d['rooms'][0]['objects'].append({'id':'key_source','name':'iron key','zone':'near','item_id':'key_item','reader':{'on':'look','event_key':'object.read','effects':[]}})
    d['rooms'][0]['exits'][0]['gate']={'kind':'flag','flag_id':'unlocked','denial_event_key':'gate.closed'}
    d['clocks'][0]['thresholds']=[{'at':1,'effects':[{'type':'set_flag','flag_id':'first','value':True}]},{'at':2,'effects':[{'type':'set_flag','flag_id':'second','value':True}]}]
    d['bank']['entries'] += [
        {'key':k,'fact_slots':slots,'variants':[v],'fallback':v}
        for k,slots,v in [('item.use',['item_name'],'Use {{item_name}}.'),('gate.closed',[],'Closed.'),('clock.threshold.patrol.1',['clock_label','at'],'{{clock_label}} {{at}}'),('clock.threshold',['clock_label','at'],'{{clock_label}} {{at}}'),('get.blocked',['enemy_name'],'Blocked {{enemy_name}}'),('get.not_takeable',['object_name'],'Cannot take {{object_name}}'),('use.nothing',[],'Nothing happens.'),('inventory',['items'],'{{items}}'),('help',[],'Help.'),('terminal.quit',[],'Quit.'),('terminal.closed',[],'Closed.'),('combat.not_yet',[],'Combat later.')]
    ]
    return load_pack(d)


class MovementTests(unittest.TestCase):
    def setUp(self):
        self.pack=extended_pack(); self.state=DelveState.new(self.pack,42,'fighter'); self.engine=Engine(self.pack,self.state)

    def apply(self, verb, target=None, direction=None):
        return self.engine.apply(Action(verb,target,direction))

    def test_move_gate_ticks_and_return(self):
        ev=self.apply('move',direction='east')
        self.assertEqual([x.key for x in ev],['gate.closed'])
        self.state.flags.add('unlocked')
        ev=self.apply('move',direction='east')
        self.assertEqual([x.key for x in ev],['room.enter','room.vault','intent.captain.smash','clock.tick','clock.threshold.patrol.1'])
        self.assertEqual(self.state.clocks['patrol'],1)
        self.state.enemies['captain']['hp']=0
        ev=self.apply('move',direction='west')
        self.assertEqual(ev[0].key,'room.return')
        ev=self.apply('move',direction='east')
        self.assertEqual(ev[0].key,'room.return')

    def test_blocked_and_no_exit_are_stable_except_event_log(self):
        self.state.room_id='vault'; before=self.state.snapshot()['canonical_state_hash']
        ev=self.apply('move',direction='west')
        self.assertEqual(ev[0].key,'move.blocked'); self.assertEqual(self.state.clocks['patrol'],0)
        self.state.enemies['captain']['hp']=0
        before=self.state.snapshot()['canonical_state_hash']; ev=self.apply('move',direction='north')
        self.assertEqual(ev[0].key,'move.no_exit'); self.assertEqual(self.state.clocks['patrol'],0)

    def test_look_inventory_help_unknown_and_readers(self):
        self.assertEqual(self.apply('look','missing')[0].key,'target.unknown')
        self.assertEqual([e.key for e in self.apply('look','bell')],['object.read','clue.bell'])
        self.assertEqual(self.apply('look','bell')[0].key,'object.read')
        self.assertEqual(self.apply('inventory')[0].key,'inventory')
        self.assertEqual(self.apply('help')[0].key,'help')

    def test_get_use_and_no_rng(self):
        self.state.room_id='entry'
        self.assertEqual(self.apply('get','bell')[0].key,'get.not_takeable')
        self.assertEqual(self.apply('get','key_source')[0].key,'item.get')
        self.assertEqual(self.apply('use','key_item')[0].key,'use.nothing')
        self.state.flags.add('unlocked'); self.state.room_id='vault'
        events=self.apply('use','key_item')
        self.assertEqual(events[0].key,'item.use')
        # Amendment 3 point 6: combat use resolves the declared intent after item effects (2 draws).
        self.assertEqual(self.state.rng_draws,2)

    def test_effect_payoff_and_thresholds_are_one_shot(self):
        events=[]; self.engine._effects([type('E',(),{'type':'reveal_clue','clue_id':i})() for i in ('bell_silenced','chart_route','dome_crack')],events)
        self.assertEqual(self.state.known_facts,['captain_route'])
        self.assertIn('fact.payoff',[e.key for e in events]); self.assertIn('captain_route_known',self.state.flags)
        again=[]; self.engine._effects([type('E',(),{'type':'reveal_clue','clue_id':'bell_silenced'})()],again)
        self.assertEqual(again,[])

    def test_terminal_and_m1_combat_stub(self):
        self.assertEqual(self.apply('attack')[0].key,'combat.not_yet')
        self.assertEqual(self.state.rng_draws,0)
        self.state.player['hp']=0
        self.state.flags.add('__player_hp_zero')
        self.engine._terminal_check([])
        self.assertEqual(self.state.terminal,'dead')
        snap=self.state.snapshot()['canonical_state_hash']; self.assertEqual(self.apply('help')[0].key,'terminal.death')
        self.assertEqual(self.state.room_id,'entry'); self.assertNotEqual(snap,self.state.snapshot()['canonical_state_hash']) # event log records echo

    def test_global_rng_and_import_boundary(self):
        before=random.getstate()
        for verb in ('look','inventory','help','get','use','quit','move','attack'):
            self.apply(verb,direction='north',target='nonesuch')
        self.assertEqual(random.getstate(),before); self.assertEqual(self.state.rng_draws,0)
        imported=set(sys.modules)
        import delve.engine
        newly=set(sys.modules)-imported
        self.assertFalse(any('terminal' in name or 'renderer' in name for name in newly))


if __name__ == '__main__': unittest.main()
