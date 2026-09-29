"""Strict JSON decoding and semantic validation for untrusted Delve packs."""
import json, re
from pathlib import Path
from . import model as m

# Engine-owned event keys and the pack contents that make each path reachable.
# Keys supplied by pack content (room descriptions, readers, telegraphs, etc.)
# remain checked by validate_pack; this table covers engine fallbacks/events.
STRUCTURAL_KEYS = {
    'room.enter': 'always', 'room.return': 'always',
    'move.blocked': 'always', 'move.no_exit': 'always',
    'target.unknown': 'always', 'object.read': 'always', 'inventory': 'always',
    'help': 'always', 'terminal.quit': 'always', 'parse.unknown_verb': 'always',
    'target.ambiguous': 'always',
    'attack.hit': 'enemies', 'attack.miss': 'enemies',
    'brace.success': 'enemies', 'brace.wasted': 'enemies',
    'shove.success': 'enemies', 'shove.fail': 'enemies',
    'throw.fizzle': 'enemies', 'throw.interrupt': 'enemies', 'enemy.defeated': 'enemies',
    'intent.cancelled': 'enemies', 'enemy.hit': 'enemies', 'enemy.miss': 'enemies',
    'retreat.blocked': 'enemies',
    'get.blocked': 'takeable_objects', 'get.not_takeable': 'takeable_objects',
    'item.get': 'takeable_objects', 'use.nothing': 'items',
    'hazard.trigger': 'hazards', 'fact.payoff': 'facts',
    'clock.tick': 'clocks', 'clock.threshold': 'thresholds',
    'clue.reveal': 'facts',
    'terminal.victory': 'always', 'terminal.death': 'always',
    'terminal.retry': 'always', 'terminal.closed': 'always',
}


def check_engine_ready(pack) -> None:
    """Require nonempty bank fallbacks for engine event paths in this pack."""
    bank = {entry.key: entry for entry in pack.bank}
    has_takeable = any(obj.item_id is not None for room in pack.rooms for obj in room.objects)
    conditions = {
        'always': True,
        'enemies': bool(pack.enemies),
        'takeable_objects': has_takeable,
        'items': bool(pack.items),
        'hazards': bool(pack.hazards),
        'facts': bool(pack.facts),
        'clocks': bool(pack.clocks),
        'thresholds': any(clock.thresholds for clock in pack.clocks),
    }
    missing = []
    for key, condition in STRUCTURAL_KEYS.items():
        if not conditions[condition]:
            continue
        if key == 'clock.threshold':
            # The engine emits a specific key when present, otherwise this fallback.
            for clock in pack.clocks:
                for threshold in clock.thresholds:
                    specific = f'clock.threshold.{clock.id}.{threshold.at}'
                    if specific not in bank and ('clock.threshold' not in bank or not bank['clock.threshold'].fallback.strip()):
                        missing.append(specific + ' (or clock.threshold)')
            continue
        entry = bank.get(key)
        if entry is None or not entry.fallback.strip():
            missing.append(key)
    # Throw readers are reached by the engine's combat throw path; their
    # content-supplied keys have the same fallback requirement as literals.
    for item in pack.items:
        if item.reader.on == 'throw':
            entry = bank.get(item.reader.event_key)
            if entry is None or not entry.fallback.strip():
                missing.append(item.reader.event_key)
    if missing:
        _err('E_BANK_STRUCTURAL_MISSING', '$.bank.entries', 'missing nonempty fallback for: ' + ', '.join(missing))


def load_engine_ready_pack(path_or_text_or_dict):
    """Load and validate a pack, then check engine-wide fallback readiness."""
    pack = load_pack(path_or_text_or_dict)
    check_engine_ready(pack)
    return pack

class PackError(ValueError):
    def __init__(self, code, path, message):
        self.code, self.path, self.message = code, path, message
        super().__init__(f"{code} at {path}: {message}")

def _err(code, path, message): raise PackError(code, path, message)
def _obj(x,p,req,opt=()):
    if not isinstance(x,dict): _err('E_SCHEMA',p,'expected object')
    missing=set(req)-x.keys(); extra=set(x)-set(req)-set(opt)
    if missing: _err('E_SCHEMA',p+'.'+sorted(missing)[0],'missing required field')
    if extra: _err('E_SCHEMA',p+'.'+sorted(extra)[0],'unknown field')
    return x
def _arr(x,p):
    if not isinstance(x,list): _err('E_SCHEMA',p,'expected array')
    return x
def _str(x,p, pattern=None):
    if not isinstance(x,str): _err('E_SCHEMA',p,'expected string')
    if pattern and not pattern.fullmatch(x): _err('E_SCHEMA',p,'invalid identifier/key')
    return x
def _int(x,p,minimum=None):
    if type(x) is not int or (minimum is not None and x<minimum): _err('E_SCHEMA',p,'expected integer in range')
    return x
def _bool(x,p):
    if type(x) is not bool: _err('E_SCHEMA',p,'expected boolean')
    return x
def _key(x,p): return _str(x,p,m.EVENT_KEY_RE)
def _id(x,p,reserved=False):
    if reserved and x=='__player_hp_zero': return x
    return _str(x,p,m.ID_RE)
def _strings(xs,p,fn=_id): return tuple(fn(v,f'{p}[{i}]') for i,v in enumerate(_arr(xs,p)))

def _effect(x,p):
    if not isinstance(x,dict): _err('E_SCHEMA',p,'expected effect object')
    typ=x.get('type')
    if typ not in m.EFFECT_TYPES: _err('E_EFFECT_UNKNOWN',p+'.type','unknown effect type')
    fields={
      'damage':({'type','target','amount'}, {'target':('player','enemy')}), 'heal':({'type','target','amount'},{'target':('player',)}),
      'tick_clock':({'type','clock_id','amount'},{}),'move_zone':({'type','actor','zone'},{'actor':('player','enemy'),'zone':('near','far','doorway','hazard')}),
      'set_flag':({'type','flag_id','value'},{}),'reveal_clue':({'type','clue_id'},{}),'spawn_object':({'type','room_id','object_id'},{}),'remove_object':({'type','room_id','object_id'},{}),
      'open_exit':({'type','room_id','direction'},{'direction':m.DIRECTIONS}),'end_run':({'type','state'},{'state':('victory','dead','quit')}),'interrupt_intent':({'type'}, {})}
    req, enums=fields[typ]; _obj(x,p,req)
    for k,vals in enums.items():
        if x[k] not in vals: _err('E_SCHEMA',p+'.'+k,'unknown vocabulary value')
    kw={'type':typ}
    for k,v in x.items():
        if k=='type': continue
        if k in ('target','actor','zone','direction','state'): kw[k]=v
        elif k=='amount': kw[k]=_int(v,p+'.amount',0)
        elif k=='value': kw[k]=_bool(v,p+'.value')
        else: kw[k]=_id(v,p+'.'+k)
    return m.Effect(**kw)
def _effects(v,p): return tuple(_effect(x,f'{p}[{i}]') for i,x in enumerate(_arr(v,p)))
def _reader(v,p):
    _obj(v,p,('on','event_key','effects'),('when_room_id','when_flag_id'))
    if v['on'] not in m.VERBS_READER_ON: _err('E_VERB_UNKNOWN',p+'.on','unknown reader verb')
    return m.Reader(_str(v['on'],p+'.on'),_key(v['event_key'],p+'.event_key'),_effects(v['effects'],p+'.effects'),_id(v['when_room_id'],p+'.when_room_id') if 'when_room_id' in v else None,_id(v['when_flag_id'],p+'.when_flag_id') if 'when_flag_id' in v else None)
def _objects(v,p):
    out=[]
    for i,x in enumerate(_arr(v,p)):
        q=f'{p}[{i}]'; _obj(x,q,('id','name','zone'),('reader','atmosphere_only','atmosphere_id','item_id'))
        reader=_reader(x['reader'],q+'.reader') if x.get('reader') is not None else None
        atm=_bool(x['atmosphere_only'],q+'.atmosphere_only') if 'atmosphere_only' in x else False
        if atm == (reader is not None): _err('E_OBJECT_READER_MISSING',q,'object must have exactly one reader or atmosphere_only')
        out.append(m.GameObject(_id(x['id'],q+'.id'),_str(x['name'],q+'.name'),_str(x['zone'],q+'.zone'),reader,atm,_id(x['atmosphere_id'],q+'.atmosphere_id') if 'atmosphere_id' in x else None,_id(x['item_id'],q+'.item_id') if 'item_id' in x else None))
    return tuple(out)
def _parse(d):
    _obj(d,'$',('schema_version','id','title','start_room_id','atmosphere_registry','rooms','enemies','hazards','clocks','items','truth','terminals','bank'),('meta',))
    if _int(d['schema_version'],'$.schema_version') != 1: _err('E_SCHEMA','$.schema_version','unsupported version')
    rooms=[]
    for i,x in enumerate(_arr(d['rooms'],'$.rooms')):
        p=f'$.rooms[{i}]'; _obj(x,p,('id','title','description_key','zones','exits','objects'),('npc_id',))
        exits=[]
        for j,e in enumerate(_arr(x['exits'],p+'.exits')):
            q=f'{p}.exits[{j}]'; _obj(e,q,('direction','to_room_id'),('gate',)); gate=None
            if 'gate' in e:
                g=e['gate']; _obj(g,q+'.gate',('kind','flag_id','denial_event_key'))
                if g['kind']!='flag': _err('E_SCHEMA',q+'.gate.kind','unknown gate kind')
                gate=m.Gate('flag',_id(g['flag_id'],q+'.gate.flag_id'),_key(g['denial_event_key'],q+'.gate.denial_event_key'))
            exits.append(m.Exit(_str(e['direction'],q+'.direction'),_id(e['to_room_id'],q+'.to_room_id'),gate))
        rooms.append(m.Room(_id(x['id'],p+'.id'),_str(x['title'],p+'.title'),_key(x['description_key'],p+'.description_key'),_strings(x['zones'],p+'.zones',lambda a,b:_str(a,b)),tuple(exits),_objects(x['objects'],p+'.objects'),_id(x['npc_id'],p+'.npc_id') if 'npc_id' in x else None))
    enemies=[]
    for i,x in enumerate(_arr(d['enemies'],'$.enemies')):
        p=f'$.enemies[{i}]'; _obj(x,p,('id','name','room_id','stats','intent_cycle','intents'),('start_zone',)); s=x['stats']; _obj(s,p+'.stats',('hp','armor_class','attack_bonus','damage_die','damage_bonus'))
        stats=m.Stats(*[_int(s[k],p+'.stats.'+k,1 if k in ('hp','armor_class','damage_die') else None) for k in ('hp','armor_class','attack_bonus','damage_die','damage_bonus')]); intents=[]
        for j,a in enumerate(_arr(x['intents'],p+'.intents')):
            q=f'{p}.intents[{j}]'; _obj(a,q,('id','type','telegraph_key','target_zone','effects','counters')); counters=[]
            for z,c in enumerate(_arr(a['counters'],q+'.counters')):
                r=f'{q}.counters[{z}]'; _obj(c,r,('action','result')); counters.append(m.Counter(_str(c['action'],r+'.action'),_str(c['result'],r+'.result')))
            intents.append(m.Intent(_id(a['id'],q+'.id'),_str(a['type'],q+'.type'),_key(a['telegraph_key'],q+'.telegraph_key'),_str(a['target_zone'],q+'.target_zone'),_effects(a['effects'],q+'.effects'),tuple(counters)))
        enemies.append(m.Enemy(_id(x['id'],p+'.id'),_str(x['name'],p+'.name'),_id(x['room_id'],p+'.room_id'),stats,_strings(x['intent_cycle'],p+'.intent_cycle'),tuple(intents),_str(x.get('start_zone','near'),p+'.start_zone')))
    hazards=[]
    for i,x in enumerate(_arr(d['hazards'],'$.hazards')):
        p=f'$.hazards[{i}]'; _obj(x,p,('id','room_id','zone','tag','event_key','trigger','effects')); t=x['trigger']; _obj(t,p+'.trigger',('action','requires_flag_id'))
        hazards.append(m.Hazard(_id(x['id'],p+'.id'),_id(x['room_id'],p+'.room_id'),_str(x['zone'],p+'.zone'),_str(x['tag'],p+'.tag'),_key(x['event_key'],p+'.event_key'),dict(t),_effects(x['effects'],p+'.effects')))
    clocks=[]
    for i,x in enumerate(_arr(d['clocks'],'$.clocks')):
        p=f'$.clocks[{i}]'; _obj(x,p,('id','label','max','start','tick_sources','thresholds')); ts=[]
        for j,t in enumerate(_arr(x['tick_sources'],p+'.tick_sources')):
            q=f'{p}.tick_sources[{j}]'; _obj(t,q,('source','amount')); ts.append(m.ClockSource(_str(t['source'],q+'.source'),_int(t['amount'],q+'.amount',1)))
        th=[]
        for j,t in enumerate(_arr(x['thresholds'],p+'.thresholds')):
            q=f'{p}.thresholds[{j}]'; _obj(t,q,('at','effects')); th.append(m.Threshold(_int(t['at'],q+'.at'),_effects(t['effects'],q+'.effects')))
        clocks.append(m.Clock(_id(x['id'],p+'.id'),_str(x['label'],p+'.label'),_int(x['max'],p+'.max',1),_int(x['start'],p+'.start'),tuple(ts),tuple(th)))
    items=[]
    for i,x in enumerate(_arr(d['items'],'$.items')):
        p=f'$.items[{i}]'; _obj(x,p,('id','name','reader'),('throw_tags','consumed_on_use'))
        consumed=_bool(x['consumed_on_use'],p+'.consumed_on_use') if 'consumed_on_use' in x else False
        items.append(m.Item(_id(x['id'],p+'.id'),_str(x['name'],p+'.name'),_reader(x['reader'],p+'.reader'),_strings(x.get('throw_tags',[]),p+'.throw_tags',lambda a,b:_str(a,b)),consumed))
    truth=d['truth']; _obj(truth,'$.truth',('facts','clues')); facts=[]
    for i,x in enumerate(_arr(truth['facts'],'$.truth.facts')):
        p=f'$.truth.facts[{i}]'; _obj(x,p,('id','payoff','clue_ids','payoff_effects'),('label',)); facts.append(m.Fact(_id(x['id'],p+'.id'),_bool(x['payoff'],p+'.payoff'),_strings(x['clue_ids'],p+'.clue_ids'),_effects(x['payoff_effects'],p+'.payoff_effects'),_str(x['label'],p+'.label') if 'label' in x else None))
    clues=[]
    for i,x in enumerate(_arr(truth['clues'],'$.truth.clues')):
        p=f'$.truth.clues[{i}]'; _obj(x,p,('id','fact_id','source_id','room_id','event_key')); clues.append(m.Clue(_id(x['id'],p+'.id'),_id(x['fact_id'],p+'.fact_id'),_id(x['source_id'],p+'.source_id'),_id(x['room_id'],p+'.room_id'),_key(x['event_key'],p+'.event_key')))
    terms=[]
    for i,x in enumerate(_arr(d['terminals'],'$.terminals')):
        p=f'$.terminals[{i}]'; _obj(x,p,('id','kind','all','event_key'),('retry_hint_key',)); preds=[]
        for j,v in enumerate(_arr(x['all'],p+'.all')):
            q=f'{p}.all[{j}]';
            if not isinstance(v,dict) or 'kind' not in v: _err('E_SCHEMA',q,'expected predicate object')
            kind=v['kind']; fields={'enemy_dead':('kind','enemy_id'),'fact_known':('kind','fact_id'),'flag_set':('kind','flag_id'),'clock_at_least':('kind','clock_id','at'),'room_is':('kind','room_id')}
            if kind not in fields: _err('E_SCHEMA',q+'.kind','unknown predicate')
            _obj(v,q,fields[kind]); pred=dict(v)
            for k,val in v.items():
                if k.endswith('_id'): pred[k]=_id(val,q+'.'+k,reserved=(kind=='flag_set' and val=='__player_hp_zero'))
                elif k=='at': pred[k]=_int(val,q+'.at')
            preds.append(pred)
        terms.append(m.Terminal(_id(x['id'],p+'.id'),_str(x['kind'],p+'.kind'),tuple(preds),_key(x['event_key'],p+'.event_key'),_key(x['retry_hint_key'],p+'.retry_hint_key') if 'retry_hint_key' in x else None))
    b=d['bank']; _obj(b,'$.bank',('entries',)); entries=[]
    for i,x in enumerate(_arr(b['entries'],'$.bank.entries')):
        p=f'$.bank.entries[{i}]'; _obj(x,p,('key','fact_slots','variants','fallback')); entries.append(m.BankEntry(_key(x['key'],p+'.key'),_strings(x['fact_slots'],p+'.fact_slots',lambda a,b:_str(a,b,re.compile(r'^[a-z][a-z0-9_]{0,31}$'))),tuple(_str(y,p+'.variants') for y in _arr(x['variants'],p+'.variants')),_str(x['fallback'],p+'.fallback')))
    if 'meta' in d and not isinstance(d['meta'],dict): _err('E_SCHEMA','$.meta','expected object')
    return m.Pack(1,_id(d['id'],'$.id'),_str(d['title'],'$.title'),_id(d['start_room_id'],'$.start_room_id'),_strings(d['atmosphere_registry'],'$.atmosphere_registry'),tuple(rooms),tuple(enemies),tuple(hazards),tuple(clocks),tuple(items),tuple(facts),tuple(clues),tuple(terms),tuple(entries),dict(d['meta']) if 'meta' in d else None)

def load_pack(path_or_text_or_dict):
    if isinstance(path_or_text_or_dict,dict): data=path_or_text_or_dict
    elif isinstance(path_or_text_or_dict,(str,Path)):
        s=str(path_or_text_or_dict)
        try:
            if isinstance(path_or_text_or_dict,Path) or (not s.lstrip().startswith(('{','[')) and Path(s).is_file()): data=json.loads(Path(s).read_text(encoding='utf-8'))
            else: data=json.loads(s)
        except (OSError, json.JSONDecodeError) as e: _err('E_SCHEMA','$',f'invalid JSON or unreadable path: {e}')
    else: _err('E_SCHEMA','$','expected path, JSON text, or dict')
    return validate_pack(_parse(data))

def validate_pack(pack):
    if not isinstance(pack,m.Pack): _err('E_SCHEMA','$','expected Pack')
    rooms={x.id:x for x in pack.rooms}; enemies={x.id:x for x in pack.enemies}; hazards={x.id:x for x in pack.hazards}; items={x.id:x for x in pack.items}; facts={x.id:x for x in pack.facts}; clues={x.id:x for x in pack.clues}; clocks={x.id:x for x in pack.clocks}; terms={x.id:x for x in pack.terminals}; objects={o.id:(r,o) for r in pack.rooms for o in r.objects}
    if pack.start_room_id not in rooms: _err('E_SCHEMA','$.start_room_id','unknown start room')
    seen={}
    all_ids=[x.id for xs in (pack.rooms,pack.enemies,pack.hazards,pack.items,pack.facts,pack.clues,pack.clocks,pack.terminals) for x in xs]
    all_ids.extend(o.id for r in pack.rooms for o in r.objects)
    for ident in all_ids:
            if ident in seen: _err('E_ID_DUPLICATE','$.','duplicate globally unique ID '+ident)
            seen[ident]=1
    item_sources={}
    for room in pack.rooms:
        for obj in room.objects:
            if obj.item_id is None: continue
            if obj.item_id not in items: _err('E_ITEM_UNKNOWN',f'object {obj.id}.item_id','unknown item '+obj.item_id)
            if obj.item_id in item_sources: _err('E_ITEM_DUPLICATE_SOURCE',f'object {obj.id}.item_id','item already has a source object')
            item_sources[obj.item_id]=obj.id
    if item_sources:
        for key in ('get.blocked','get.not_takeable','use.nothing'):
            _needbank({e.key:e for e in pack.bank},key,f'bank {key}')
    # Count before resolving individual clue/effect references so a deleted clue
    # is reported as an insufficient payoff source, as the spec mutation requires.
    reachable={pack.start_room_id}; todo=[pack.start_room_id]
    while todo:
        here=todo.pop()
        for ex in rooms[here].exits:
            if ex.to_room_id in rooms and ex.to_room_id not in reachable: reachable.add(ex.to_room_id); todo.append(ex.to_room_id)
    for f in pack.facts:
        sources={clues[c].source_id for c in f.clue_ids if c in clues and clues[c].room_id in reachable}
        if len(sources)<3: _err('E_FACT_CLUE_COUNT',f'fact {f.id}.clue_ids','payoff needs three reachable unique clue sources')
    bank={e.key:e for e in pack.bank}
    if len(bank)!=len(pack.bank): _err('E_SCHEMA','$.bank.entries','duplicate bank key')
    for r in pack.rooms:
        for z in r.zones:
            if z not in m.ZONES: _err('E_SCHEMA',f'room {r.id}.zones','unknown zone')
        for e in r.exits:
            if e.direction not in m.DIRECTIONS: _err('E_SCHEMA',f'room {r.id}.exits','unknown direction')
            if e.to_room_id not in rooms: _err('E_EXIT_DANGLING',f'room {r.id}.exits','unknown destination '+e.to_room_id)
            if e.gate and e.gate.flag_id=='': _err('E_SCHEMA','$.rooms.exits.gate.flag_id','invalid flag')
        for o in r.objects:
            if o.zone not in r.zones: _err('E_SCHEMA',f'object {o.id}.zone','zone absent from room')
            if o.atmosphere_only and o.atmosphere_id not in pack.atmosphere_registry: _err('E_ATMOSPHERE_UNREGISTERED',f'object {o.id}.atmosphere_id','atmosphere is not registered')
    for e in pack.enemies:
        if e.room_id not in rooms: _err('E_SCHEMA',f'enemy {e.id}.room_id','unknown room')
        if not {'near','far','doorway'}.issubset(rooms[e.room_id].zones): _err('E_SCHEMA',f'enemy {e.id}.room_id','enemy room must have near/far/doorway zones')
        im={i.id:i for i in e.intents}
        if not set(e.intent_cycle)<=im.keys(): _err('E_SCHEMA',f'enemy {e.id}.intent_cycle','unknown intent')
        for i in e.intents:
            if i.type not in m.INTENT_TYPES or i.target_zone not in m.ZONES: _err('E_SCHEMA',f'intent {i.id}','unknown intent vocabulary')
            if i.telegraph_key not in bank: _err('E_INTENT_TELEGRAPH_MISSING',f'intent {i.id}.telegraph_key','missing bank entry')
    for h in pack.hazards:
        if h.tag not in m.HAZARD_TAGS: _err('E_HAZARD_TAG_UNKNOWN',f'hazard {h.id}.tag','unknown hazard tag')
        if h.room_id not in rooms: _err('E_SCHEMA',f'hazard {h.id}.room_id','unknown room')
        if 'hazard' not in rooms[h.room_id].zones: _err('E_SCHEMA',f'hazard {h.id}.room_id','hazard room lacks hazard zone')
    for c in pack.clocks:
        if c.start<0 or c.start>c.max: _err('E_CLOCK_THRESHOLD_RANGE',f'clock {c.id}.start','start outside 0..max')
        ats=[t.at for t in c.thresholds]
        if any(a<1 or a>c.max for a in ats) or ats!=sorted(set(ats)): _err('E_CLOCK_THRESHOLD_RANGE',f'clock {c.id}.thresholds','thresholds must increase within 1..max')
    for obj in list(objects.values()):
        r,o=obj
        if o.reader: _validate_reader(o.reader,rooms,items,clues,clocks,objects,bank,f'object {o.id}')
    for it in pack.items: _validate_reader(it.reader,rooms,items,clues,clocks,objects,bank,f'item {it.id}')
    for h in pack.hazards:
        _needbank(bank,h.event_key,f'hazard {h.id}.event_key')
        _validate_effects(h.effects,rooms,clues,clocks,objects)
    for r in pack.rooms: _needbank(bank,r.description_key,f'room {r.id}.description_key')
    for clue in pack.clues:
        if clue.fact_id not in facts or clue.room_id not in rooms or clue.source_id not in objects and clue.source_id not in items: _err('E_SCHEMA',f'clue {clue.id}','unresolved clue reference')
        source_room=objects[clue.source_id][0].id if clue.source_id in objects else next((r.id for r in pack.rooms if any(clue.source_id==o.id for o in r.objects)),None)
        if source_room!=clue.room_id: _err('E_SCHEMA',f'clue {clue.id}.room_id','source is not in declared room')
        _needbank(bank,clue.event_key,f'clue {clue.id}.event_key')
    # Static reachability deliberately treats gated exits as open.
    reachable={pack.start_room_id}; todo=[pack.start_room_id]
    while todo:
        here=todo.pop()
        for ex in rooms[here].exits:
            if ex.to_room_id not in reachable: reachable.add(ex.to_room_id); todo.append(ex.to_room_id)
    for f in pack.facts:
        listed=[clues[c] for c in f.clue_ids if c in clues]
        if len(listed)!=len(f.clue_ids) or len({c.source_id for c in listed if c.room_id in reachable})<3: _err('E_FACT_CLUE_COUNT',f'fact {f.id}.clue_ids','payoff needs three reachable unique clue sources')
        _validate_effects(f.payoff_effects,rooms,clues,clocks,objects)
    for t in pack.terminals:
        if t.kind not in ('victory','death','dead','quit','playing'): _err('E_SCHEMA',f'terminal {t.id}.kind','unknown terminal kind')
        _needbank(bank,t.event_key,f'terminal {t.id}.event_key')
        if t.retry_hint_key: _needbank(bank,t.retry_hint_key,f'terminal {t.id}.retry_hint_key')
        for p in t.all: _predicate(p,rooms,enemies,facts,clocks)
        if t.kind=='victory':
            room_requirements=[p['room_id'] for p in t.all if p['kind']=='room_is']
            if len(set(room_requirements)) > 1: _err('E_TERMINAL_UNREACHABLE',f'terminal {t.id}','conflicting room predicates')
            possible=True
            for p in t.all:
                if p['kind']=='room_is' and p['room_id'] not in reachable: possible=False
                if p['kind']=='enemy_dead' and enemies[p['enemy_id']].room_id not in reachable: possible=False
            if not possible: _err('E_TERMINAL_UNREACHABLE',f'terminal {t.id}','victory predicate cannot be reached')
    # Every bank string's placeholders must exactly equal the declared slot set.
    for e in pack.bank:
        if not e.fallback.strip(): _err('E_BANK_FALLBACK_MISSING',f'bank {e.key}.fallback','fallback must be nonempty')
        declared=set(e.fact_slots)
        for value in (*e.variants,e.fallback):
            slots=set(re.findall(r'{{([^{}]+)}}',value))
            if slots!=declared or '{{' in re.sub(r'{{[^{}]+}}','',value) or '}}' in re.sub(r'{{[^{}]+}}','',value): _err('E_BANK_SLOT',f'bank {e.key}','placeholder/slot mismatch')
    return pack

def _needbank(bank,key,path):
    if key not in bank: _err('E_BANK_FALLBACK_MISSING',path,'missing bank entry')
    if not bank[key].fallback.strip(): _err('E_BANK_FALLBACK_MISSING',path,'empty fallback')
def _validate_reader(r,rooms,items,clues,clocks,objects,bank,path):
    _needbank(bank,r.event_key,path+'.event_key')
    if r.when_room_id and r.when_room_id not in rooms: _err('E_SCHEMA',path+'.when_room_id','unknown room')
    for e in r.effects: _validate_effects((e,),rooms,clues,clocks,objects)
def _validate_effects(effects,rooms,clues,clocks,objects):
    for e in effects:
        if e.type=='tick_clock' and e.clock_id not in clocks: _err('E_SCHEMA','$.effects.clock_id','unknown clock')
        if e.type=='reveal_clue' and e.clue_id not in clues: _err('E_SCHEMA','$.effects.clue_id','unknown clue')
        if e.type in ('spawn_object','remove_object') and (e.room_id not in rooms or e.object_id not in objects): _err('E_SCHEMA','$.effects','unknown room/object')
        if e.type=='open_exit' and (e.room_id not in rooms or not any(x.direction==e.direction for x in rooms[e.room_id].exits)): _err('E_SCHEMA','$.effects','unknown exit')
def _predicate(p,rooms,enemies,facts,clocks):
    k=p['kind']; field={'enemy_dead':'enemy_id','fact_known':'fact_id','flag_set':'flag_id','clock_at_least':'clock_id','room_is':'room_id'}[k]; val=p[field]
    table={'enemy_dead':enemies,'fact_known':facts,'clock_at_least':clocks,'room_is':rooms}
    if k in table and val not in table[k]: _err('E_SCHEMA','$.terminals.all.'+field,'unknown predicate target')
    if k=='clock_at_least' and p['at']>clocks[val].max: _err('E_SCHEMA','$.terminals.all.at','threshold exceeds clock max')
    return True
