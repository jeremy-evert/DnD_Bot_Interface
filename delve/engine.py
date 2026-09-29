"""Authoritative M1 exploration and effect execution."""
from dataclasses import dataclass, asdict

from .model import DIRECTIONS
from .state import roll_die


@dataclass(frozen=True)
class Action:
    verb: str
    target_id: str | None = None
    direction: str | None = None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Event:
    type: str
    key: str
    fact_slots: dict
    numbers: dict
    effects: list

    def to_dict(self):
        return asdict(self)


class Engine:
    def __init__(self, pack, state):
        self.pack, self.state = pack, state
        self.rooms = {x.id: x for x in pack.rooms}
        self.items = {x.id: x for x in pack.items}
        self.enemies = {x.id: x for x in pack.enemies}
        self.clues = {x.id: x for x in pack.clues}
        self.bank = {x.key for x in pack.bank}

    def _event(self, key, slots=None, typ=None, numbers=None, effects=None):
        return Event(typ or key.replace('.', '_'), key, slots or {}, numbers or {}, effects or [])

    def apply(self, action):
        if isinstance(action, dict):
            action = Action(**action)
        if not isinstance(action, Action):
            raise TypeError('action must be Action')
        s = self.state
        if s.terminal != 'playing':
            e = self._event('terminal.' + ('victory' if s.terminal == 'victory' else 'death' if s.terminal == 'dead' else 'closed'))
            return self._record([e])
        verb = action.verb
        events = []
        foe_at_start = self._living_enemy()
        intent_at_start = self._current_intent(foe_at_start) if foe_at_start else None
        valid = True
        if verb in ('n','s','e','w','go','move'):
            direction = action.direction or {'n':'north','s':'south','e':'east','w':'west'}.get(verb)
            if direction not in DIRECTIONS:
                return self._record([self._event('move.no_exit', {'direction': str(direction)})])
            foe = self._living_enemy()
            if foe:
                return self._record([self._event('move.blocked', {'enemy_name': foe.name})])
            ex = next((x for x in self.rooms[s.room_id].exits if x.direction == direction), None)
            if ex is None:
                return self._record([self._event('move.no_exit', {'direction': direction})])
            if ex.gate and ex.gate.flag_id not in s.flags:
                return self._record([self._event(ex.gate.denial_event_key)])
            s.room_id = ex.to_room_id
            s.player['zone'] = 'doorway' if self._living_enemy() else 'near'
            seen = s.bank_memory.setdefault('__visited_rooms', [])
            key = 'room.return' if s.room_id in seen or s.room_id == self.pack.start_room_id else 'room.enter'
            if s.room_id not in seen: seen.append(s.room_id)
            events.append(self._event(key, {'room_name': self.rooms[s.room_id].title}))
            events.append(self._event(self.rooms[s.room_id].description_key, {'room_name': self.rooms[s.room_id].title}, typ='room_description'))
            enemy = self._living_enemy()
            if enemy:
                st = s.enemies[enemy.id]
                intent = next((i for i in enemy.intents if i.id == st['current_intent_id']), None)
                if intent:
                    events.append(self._event(intent.telegraph_key, {'enemy_name':enemy.name}, typ='enemy_intent'))
            self._ticks('move', events)
        elif verb in ('look','x','examine'):
            if not action.target_id:
                room = self.rooms[s.room_id]
                events.append(self._event(room.description_key, {'room_name': room.title}, typ='room_description'))
            else:
                obj = next((o for r in self.pack.rooms if r.id == s.room_id for o in r.objects if o.id == action.target_id and o.id in s.present_objects[s.room_id]), None)
                if obj is None: return self._record([self._event('target.unknown', {'target': action.target_id})])
                reader = obj.reader
                if reader and reader.on == 'look' and self._reader_ready(reader):
                    events.append(self._event(reader.event_key, {'object_name': obj.name}))
                    self._effects(reader.effects, events)
                else: events.append(self._event('object.read', {'object_name': obj.name}))
        elif verb in ('inventory','i'):
            events.append(self._event('inventory', {'items': ', '.join(self.items[i].name for i in s.inventory)}))
        elif verb in ('help','?'):
            events.append(self._event('help'))
        elif verb in ('quit','q'):
            s.terminal = 'quit'; events.append(self._event('terminal.quit'))
        elif verb in ('get','take','g'):
            events.extend(self._get(action.target_id))
        elif verb in ('use','u'):
            events.extend(self._use(action.target_id))
            valid = bool(action.target_id in s.inventory)
            if valid and foe_at_start and intent_at_start:
                self._finish_round(foe_at_start, intent_at_start, events)
        elif verb in ('attack','shove','brace','throw','retreat'):
            if verb == 'attack':
                if not foe_at_start or not intent_at_start:
                    events.append(self._event('combat.not_yet')); valid=False
                else:
                    self._attack(foe_at_start, intent_at_start, events)
                    if self._living_enemy() is foe_at_start:
                        self._finish_round(foe_at_start, intent_at_start, events)
            elif verb == 'brace':
                if not foe_at_start or not intent_at_start:
                    events.append(self._event('combat.not_yet')); valid=False
                else:
                    counter = self._brace(foe_at_start, intent_at_start, events)
                    if counter != 'cancel' and self._living_enemy() is foe_at_start:
                        self._finish_round(foe_at_start, intent_at_start, events, counter)
                    elif counter == 'cancel' and self._living_enemy() is foe_at_start:
                        self._advance_and_declare(foe_at_start, events)
            elif verb == 'retreat':
                if not self._retreat(action.direction, foe_at_start, intent_at_start, events): valid=False
            else:
                # M1.6 owns shove and throw.
                events.append(self._event('combat.not_yet')); valid=False
        else:
            events.append(self._event('target.unknown', {'target': action.target_id or verb}))
        if valid:
            s.turn += 1
            self._terminal_check(events)
        return self._record(events)

    def _current_intent(self, enemy):
        if enemy is None: return None
        ident=self.state.enemies[enemy.id]['current_intent_id']
        return next((i for i in enemy.intents if i.id==ident),None)

    def _declare_intent(self, enemy):
        st=self.state.enemies[enemy.id]
        if st['hp']<=0 or not enemy.intent_cycle:
            st['current_intent_id']=None; return None
        ident=enemy.intent_cycle[st['intent_index'] % len(enemy.intent_cycle)]
        st['current_intent_id']=ident
        intent=next(i for i in enemy.intents if i.id==ident)
        return intent

    def _advance_and_declare(self, enemy, events):
        st=self.state.enemies[enemy.id]
        st['intent_index']=(st['intent_index']+1) % max(1,len(enemy.intent_cycle))
        intent=self._declare_intent(enemy)
        if intent: events.append(self._event(intent.telegraph_key,{'enemy_name':enemy.name},typ='enemy_intent'))

    def _attack(self, enemy, intent, events):
        s=self.state; st=s.enemies[enemy.id]
        die=roll_die(s,20); damage_die=roll_die(s,s.player['damage_die'])
        ac=enemy.stats.armor_class+(2 if intent.type=='guard' else 0)
        total=die+s.player['attack_bonus']; margin=total-ac
        hit=die==20 or (die!=1 and total>=ac)
        if hit:
            damage=max(1,damage_die+s.player['damage_bonus'])
            st['hp']=max(0,st['hp']-damage); st['alive']=st['hp']>0
            events.append(self._event('attack.hit',{'enemy_name':enemy.name,'damage':damage},numbers={'roll':die,'total':total,'damage':damage}))
            if not st['alive']: st['current_intent_id']=None
        else:
            events.append(self._event('attack.miss',{'margin':abs(margin)},numbers={'roll':die,'total':total,'margin':margin}))

    def _brace(self, enemy, intent, events):
        if intent.type=='strike':
            events.append(self._event('brace.success')); return 'halve'
        if intent.type=='smash':
            events.append(self._event('brace.success')); return 'negate'
        if intent.type=='grab':
            events.append(self._event('brace.success')); return 'resist'
        if intent.type=='rush':
            events.append(self._event('brace.success')); return 'cancel'
        events.append(self._event('brace.wasted')); return None

    def _resolve_intent(self, enemy, counter=None, events=None):
        if events is None: events=[]
        s=self.state; st=s.enemies[enemy.id]; intent=self._current_intent(enemy)
        if st['hp']<=0 or intent is None: return events
        damages=[e.amount for e in intent.effects if e.type=='damage' and e.target=='player']
        # A damaging intent always consumes both dice, including a negated hit.
        roll=roll_die(s,20); die=roll_die(s,enemy.stats.damage_die)
        total=roll+enemy.stats.attack_bonus; ac=s.player['armor_class']
        hit=roll==20 or (roll!=1 and total>=ac)
        if not hit and damages:
            events.append(self._event('enemy.miss',{'enemy_name':enemy.name},numbers={'roll':roll,'total':total}))
            return events
        if damages:
            damage=max(1,die+enemy.stats.damage_bonus)+sum(damages)
            if counter=='halve': damage//=2
            if counter in ('negate','resist'): damage=0
            if damage:
                s.player['hp']=max(0,s.player['hp']-damage)
                if s.player['hp']==0:
                    s.flags.add('__player_hp_zero')
                    self._last_death_cause=f'{enemy.name} {intent.type}'
                events.append(self._event('enemy.hit',{'enemy_name':enemy.name,'damage':damage},numbers={'roll':roll,'total':total,'damage':damage}))
        for effect in intent.effects:
            if effect.type!='damage': self._effects([effect],events)
        return events

    def _finish_round(self, enemy, intent, events, counter=None):
        if self.state.enemies[enemy.id]['current_intent_id'] != intent.id: return
        self._resolve_intent(enemy,counter,events)
        self._advance_and_declare(enemy,events)

    def _retreat(self, direction, enemy, intent, events):
        s=self.state
        if not enemy or not intent or s.player['zone']!='doorway' or intent.type=='grab':
            events.append(self._event('retreat.blocked')); return False
        ex=next((x for x in self.rooms[s.room_id].exits if x.direction==direction and x.gate is None),None)
        if ex is None:
            events.append(self._event('retreat.blocked')); return False
        s.room_id=ex.to_room_id; s.player['zone']='near'
        events.append(self._event('room.return',{'room_name':self.rooms[s.room_id].title}))
        events.append(self._event(self.rooms[s.room_id].description_key,{'room_name':self.rooms[s.room_id].title},typ='room_description'))
        self._ticks('retreat',events)
        return True

    def _record(self, events):
        self.state.event_log.extend(e.to_dict() for e in events)
        return events

    def _living_enemy(self):
        return next((e for e in self.pack.enemies if e.room_id == self.state.room_id and self.state.enemies[e.id]['hp'] > 0), None)

    def _reader_ready(self, reader):
        return (reader.when_room_id is None or reader.when_room_id == self.state.room_id) and (reader.when_flag_id is None or reader.when_flag_id in self.state.flags)

    def _get(self, target):
        s = self.state
        obj = next((o for o in self.rooms[s.room_id].objects if o.id == target and o.id in s.present_objects[s.room_id]), None)
        if obj is None: return [self._event('target.unknown', {'target': target or ''})]
        foe = self._living_enemy()
        if foe: return [self._event('get.blocked', {'enemy_name': foe.name})]
        if obj.item_id is None: return [self._event('get.not_takeable', {'object_name': obj.name})]
        s.inventory.append(obj.item_id); s.present_objects[s.room_id].remove(obj.id)
        return [self._event('item.get', {'item_name': self.items[obj.item_id].name})]

    def _use(self, target):
        if target not in self.state.inventory:
            return [self._event('target.unknown', {'target': target or ''})]
        item = self.items[target]; reader = item.reader
        if reader.on != 'use' or not self._reader_ready(reader): return [self._event('use.nothing')]
        events = [self._event(reader.event_key, {'item_name': item.name})]
        self._effects(reader.effects, events)
        return events

    def _effects(self, effects, events):
        s = self.state
        for e in effects:
            if e.type == 'damage':
                if e.target == 'player':
                    s.player['hp'] = max(0, s.player['hp'] - e.amount)
                    if s.player['hp'] == 0: s.flags.add('__player_hp_zero')
                elif e.target in s.enemies:
                    ent=s.enemies[e.target]; ent['hp']=max(0,ent['hp']-e.amount); ent['alive']=ent['hp']>0
            elif e.type == 'heal': s.player['hp'] = min(s.player['max_hp'], s.player['hp'] + e.amount)
            elif e.type == 'tick_clock': self._tick(e.clock_id, e.amount, events)
            elif e.type == 'move_zone':
                if e.actor == 'player': s.player['zone'] = e.zone
                elif e.actor in s.enemies: s.enemies[e.actor]['zone'] = e.zone
            elif e.type == 'set_flag':
                if e.value: s.flags.add(e.flag_id)
                else: s.flags.discard(e.flag_id)
            elif e.type == 'reveal_clue': self._reveal(e.clue_id, events)
            elif e.type == 'spawn_object':
                if e.object_id not in s.present_objects[e.room_id]: s.present_objects[e.room_id].append(e.object_id)
            elif e.type == 'remove_object':
                if e.object_id in s.present_objects[e.room_id]: s.present_objects[e.room_id].remove(e.object_id)
            elif e.type == 'open_exit':
                s.flags.add('__open_exit:' + e.room_id + ':' + e.direction)
            elif e.type == 'end_run': s.terminal = e.state
            elif e.type == 'interrupt_intent':
                foe=self._living_enemy()
                if foe: s.enemies[foe.id]['current_intent_id'] = None

    def _reveal(self, clue_id, events):
        s = self.state
        if clue_id in s.known_clues: return
        clue = self.clues[clue_id]; s.known_clues.append(clue_id)
        events.append(self._event(clue.event_key, typ='clue_reveal'))
        for fact in self.pack.facts:
            if fact.payoff and fact.id not in s.known_facts and set(fact.clue_ids).issubset(s.known_clues):
                s.known_facts.append(fact.id)
                events.append(self._event('fact.payoff', {'fact_label': fact.label or fact.id}))
                self._effects(fact.payoff_effects, events)

    def _ticks(self, source, events):
        for clock in self.pack.clocks:
            amount=sum(x.amount for x in clock.tick_sources if x.source == source)
            if amount: self._tick(clock.id, amount, events)

    def _tick(self, clock_id, amount, events):
        clock=next(x for x in self.pack.clocks if x.id==clock_id); s=self.state
        before=s.clocks[clock_id]; after=min(clock.max,before+amount); s.clocks[clock_id]=after
        if after == before: return
        events.append(self._event('clock.tick', {'clock_label':clock.label,'value':after,'max':clock.max}))
        for threshold in clock.thresholds:
            if before < threshold.at <= after:
                key=f'clock.threshold.{clock_id}.{threshold.at}'
                if key not in self.bank: key='clock.threshold'
                events.append(self._event(key, {'clock_label':clock.label,'at':threshold.at}))
                self._effects(threshold.effects,events)

    def _terminal_check(self, events):
        s=self.state
        for terminal in self.pack.terminals:
            if terminal.kind in ('death','dead') and s.player['hp'] <= 0:
                s.terminal='dead'
                cause=getattr(self,'_last_death_cause','your wounds')
                events.append(self._event('terminal.death', {'cause':cause})); return
        for terminal in self.pack.terminals:
            if terminal.kind != 'victory': continue
            if all(self._predicate(p) for p in terminal.all):
                s.terminal='victory'; events.append(self._event('terminal.victory')); return

    def _predicate(self, p):
        s=self.state; k=p['kind']
        return {'enemy_dead':lambda:s.enemies[p['enemy_id']]['hp']<=0,'fact_known':lambda:p['fact_id'] in s.known_facts,'flag_set':lambda:p['flag_id'] in s.flags,'clock_at_least':lambda:s.clocks[p['clock_id']]>=p['at'],'room_is':lambda:s.room_id==p['room_id']}[k]()
