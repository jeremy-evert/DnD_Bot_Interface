<!-- Binding interface spec for Fast Delve M1, authored by Terra/Penny (plan terra-fast-delve-01), approved by Ivy 2026-09-29. Quality yardstick: docs/QUALITY_VISION.md -->
# Fast Delve M1 — Binding Interface Spec

`spec_id`: `terra-fast-delve-01-m1-binding`  
`status`: binding for all M1 builders  
`scope`: new `delve/` only; `dnd_combat/` remains frozen at `94af79a`.

Python owns all state. Packs are untrusted data. No live LLM calls, GUI, networking, persistence, accounts, or `dnd_combat` changes.

## 1. Data model

All pack JSON is UTF-8, strict JSON objects (`additionalProperties: false` except optional `meta`), and must validate before a run begins.

| Rule | Value |
|---|---|
| `ID` | `^[a-z][a-z0-9_]{1,31}$` |
| event key | `^[a-z][a-z0-9_.]{1,63}$` |
| text key | event key |
| directions | `north`, `south`, `east`, `west` |
| zones | `near`, `far`, `doorway`, `hazard` |
| terminal states | `playing`, `victory`, `dead`, `quit` |
| unknown field/reference/vocabulary value | reject; never ignore |

### Pack shape

```json
{
  "schema_version": 1,
  "id": "ID",
  "title": "string",
  "start_room_id": "ID",
  "atmosphere_registry": ["ID"],
  "rooms": ["Room"],
  "enemies": ["Enemy"],
  "hazards": ["Hazard"],
  "clocks": ["Clock"],
  "items": ["Item"],
  "truth": {"facts": ["Fact"], "clues": ["Clue"]},
  "terminals": ["Terminal"],
  "bank": {"entries": ["BankEntry"]},
  "meta": {"authoring_receipt": "optional string"}
}
```

| Type | Required fields | Optional fields |
|---|---|---|
| `Room` | `id`, `title`, `description_key`, `zones`, `exits`, `objects` | `npc_id` |
| `Exit` | `direction`, `to_room_id` | `gate` |
| `Gate` | `kind:"flag"`, `flag_id`, `denial_event_key` | — |
| `Object` | `id`, `name`, `zone` | exactly one of `reader` or `atmosphere_only:true`; atmosphere objects also require `atmosphere_id` |
| `Reader` | `on`, `event_key`, `effects` | `when_room_id`, `when_flag_id` |
| `Enemy` | `id`, `name`, `room_id`, `stats`, `intent_cycle`, `intents` | `start_zone` (default `near`) |
| `Stats` | `hp`, `armor_class`, `attack_bonus`, `damage_die`, `damage_bonus` | — |
| `Intent` | `id`, `type`, `telegraph_key`, `target_zone`, `effects`, `counters` | — |
| `Hazard` | `id`, `room_id`, `zone:"hazard"`, `tag`, `event_key`, `trigger`, `effects` | — |
| `Clock` | `id`, `label`, `max`, `start`, `tick_sources`, `thresholds` | — |
| `Item` | `id`, `name`, `reader` | `throw_tags` |
| `Fact` | `id`, `payoff:true`, `clue_ids`, `payoff_effects` | `label` |
| `Clue` | `id`, `fact_id`, `source_id`, `room_id`, `event_key` | — |
| `Terminal` | `id`, `kind`, `all`, `event_key` | `retry_hint_key` for `kind:"death"` |
| `BankEntry` | `key`, `fact_slots`, `variants`, `fallback` | — |

`Room.zones` is a unique nonempty array of zone values. Every room containing an enemy must contain `near`, `far`, and `doorway`; a room with a hazard must contain `hazard`.

Effects are JSON objects from the closed vocabulary below. Effect execution happens only inside `Engine.apply()`.

```json
{"type":"damage","target":"player|enemy","amount":1}
{"type":"heal","target":"player","amount":1}
{"type":"tick_clock","clock_id":"ID","amount":1}
{"type":"move_zone","actor":"player|enemy","zone":"near|far|doorway|hazard"}
{"type":"set_flag","flag_id":"ID","value":true}
{"type":"reveal_clue","clue_id":"ID"}
{"type":"spawn_object","room_id":"ID","object_id":"ID"}
{"type":"remove_object","room_id":"ID","object_id":"ID"}
{"type":"open_exit","room_id":"ID","direction":"north|south|east|west"}
{"type":"end_run","state":"victory|dead|quit"}
{"type":"interrupt_intent"}
```

### Validation requirements

- IDs are globally unique across rooms, enemies, hazards, items, facts, clues, clocks, terminals, and objects.
- Every exit destination, gate flag, effect reference, room/object/item source, bank key, and terminal predicate target resolves.
- A non-atmosphere object/item must have one `reader`; an atmosphere object must have a registered `atmosphere_id`.
- `Reader.on` is only `look`, `use`, or `throw`.
- A payoff fact has at least three unique, reachable clue sources before victory. Re-reading one source never counts twice.
- Every `telegraph_key`, room description key, clue key, hazard key, terminal key, and reader key has a bank entry with nonempty fallback.
- Terminals use `all`, an array of predicates: `enemy_dead`, `fact_known`, `flag_set`, `clock_at_least`, `room_is`.
- A victory terminal must be reachable from `start_room_id` in the static room/action graph.
- Clock thresholds are strictly increasing integers in `1..max`; `start` is in `0..max`.

### Complete valid example

```json
{
  "schema_version": 1,
  "id": "two_room_demo",
  "title": "Hollow Lesson",
  "start_room_id": "entry",
  "atmosphere_registry": [],
  "rooms": [
    {
      "id": "entry",
      "title": "Cracked Entry",
      "description_key": "room.entry",
      "zones": ["near", "far", "doorway"],
      "exits": [{"direction": "east", "to_room_id": "vault"}],
      "objects": [
        {"id": "bell", "name": "clapperless bell", "zone": "near", "reader": {"on": "look", "event_key": "object.read", "effects": [{"type": "reveal_clue", "clue_id": "bell_silenced"}]}},
        {"id": "chart", "name": "star chart", "zone": "far", "reader": {"on": "look", "event_key": "object.read", "effects": [{"type": "reveal_clue", "clue_id": "chart_route"}]}},
        {"id": "dome", "name": "collapsed dome", "zone": "doorway", "reader": {"on": "look", "event_key": "object.read", "effects": [{"type": "reveal_clue", "clue_id": "dome_crack"}]}}
      ]
    },
    {
      "id": "vault",
      "title": "Hollow Vault",
      "description_key": "room.vault",
      "zones": ["near", "far", "doorway", "hazard"],
      "exits": [{"direction": "west", "to_room_id": "entry"}],
      "objects": []
    }
  ],
  "enemies": [{
    "id": "captain",
    "name": "Hobgoblin Captain",
    "room_id": "vault",
    "start_zone": "doorway",
    "stats": {"hp": 18, "armor_class": 14, "attack_bonus": 5, "damage_die": 8, "damage_bonus": 2},
    "intent_cycle": ["smash"],
    "intents": [{
      "id": "smash",
      "type": "smash",
      "telegraph_key": "intent.captain.smash",
      "target_zone": "doorway",
      "effects": [{"type": "damage", "target": "player", "amount": 0}],
      "counters": [{"action": "brace", "result": "negate"}, {"action": "shove", "result": "send_to_hazard_if_route_known"}]
    }]
  }],
  "hazards": [{
    "id": "vault_collapse",
    "room_id": "vault",
    "zone": "hazard",
    "tag": "collapse",
    "event_key": "hazard.collapse",
    "trigger": {"action": "shove", "requires_flag_id": "captain_route_known"},
    "effects": [{"type": "damage", "target": "enemy", "amount": 6}]
  }],
  "clocks": [{
    "id": "patrol",
    "label": "PATROL",
    "max": 4,
    "start": 0,
    "tick_sources": [{"source": "move", "amount": 1}, {"source": "retreat", "amount": 1}],
    "thresholds": [{"at": 2, "effects": [{"type": "set_flag", "flag_id": "patrol_alert", "value": true}]}]
  }],
  "items": [],
  "truth": {
    "facts": [{
      "id": "captain_route",
      "label": "The captain can be shoved beneath the collapse.",
      "payoff": true,
      "clue_ids": ["bell_silenced", "chart_route", "dome_crack"],
      "payoff_effects": [{"type": "set_flag", "flag_id": "captain_route_known", "value": true}]
    }],
    "clues": [
      {"id": "bell_silenced", "fact_id": "captain_route", "source_id": "bell", "room_id": "entry", "event_key": "clue.bell"},
      {"id": "chart_route", "fact_id": "captain_route", "source_id": "chart", "room_id": "entry", "event_key": "clue.chart"},
      {"id": "dome_crack", "fact_id": "captain_route", "source_id": "dome", "room_id": "entry", "event_key": "clue.dome"}
    ]
  },
  "terminals": [
    {"id": "victory", "kind": "victory", "all": [{"kind": "enemy_dead", "enemy_id": "captain"}, {"kind": "fact_known", "fact_id": "captain_route"}], "event_key": "terminal.victory"},
    {"id": "death", "kind": "death", "all": [{"kind": "flag_set", "flag_id": "__player_hp_zero"}], "event_key": "terminal.death", "retry_hint_key": "terminal.retry"}
  ],
  "bank": {
    "entries": [
      {"key":"room.entry","fact_slots":[],"variants":["Rain taps the cracked stone."],"fallback":"Rain taps the cracked stone."},
      {"key":"room.vault","fact_slots":[],"variants":["The vault doorway is scarred by old impacts."],"fallback":"The vault doorway is scarred by old impacts."},
      {"key":"object.read","fact_slots":["object_name"],"variants":["You study {{object_name}}."],"fallback":"You study {{object_name}}."},
      {"key":"clue.bell","fact_slots":[],"variants":["The bell was silenced before the captain passed."],"fallback":"The bell was silenced before the captain passed."},
      {"key":"clue.chart","fact_slots":[],"variants":["The chart marks the vault doorway beneath the cracked dome."],"fallback":"The chart marks the vault doorway beneath the cracked dome."},
      {"key":"clue.dome","fact_slots":[],"variants":["The dome fracture points directly over the vault approach."],"fallback":"The dome fracture points directly over the vault approach."},
      {"key":"intent.captain.smash","fact_slots":[],"variants":["The Captain winds up to SMASH the doorway — brace or shove!"],"fallback":"The Captain winds up to SMASH the doorway — brace or shove!"},
      {"key":"hazard.collapse","fact_slots":[],"variants":["Stone drops onto the Captain's hollow pauldron."],"fallback":"Stone drops onto the Captain's hollow pauldron."},
      {"key":"terminal.victory","fact_slots":[],"variants":["The vault falls quiet. You found the route."],"fallback":"The vault falls quiet. You found the route."},
      {"key":"terminal.death","fact_slots":["cause"],"variants":["You fall to {{cause}}."],"fallback":"You fall to {{cause}}."},
      {"key":"terminal.retry","fact_slots":[],"variants":["Retry: read the room, then counter the declared intent."],"fallback":"Retry: read the room, then counter the declared intent."}
    ]
  }
}
```

### Required invalid mutations

| Mutation | Required rejection |
|---|---|
| exit `to_room_id:"missing"` | `E_EXIT_DANGLING` |
| reader effect `{"type":"explode"}` | `E_EFFECT_UNKNOWN` |
| make victory predicates impossible | `E_TERMINAL_UNREACHABLE` |
| remove `terminal.victory.fallback` | `E_BANK_FALLBACK_MISSING` |
| set atmosphere object `atmosphere_id:"mist"` without registry entry | `E_ATMOSPHERE_UNREGISTERED` |
| remove one `captain_route` clue | `E_FACT_CLUE_COUNT` |
| rename `chart` to `bell` | `E_ID_DUPLICATE` |
| reader `on:"sing"` | `E_VERB_UNKNOWN` |
| clock threshold `at:5` with `max:4` | `E_CLOCK_THRESHOLD_RANGE` |
| remove bank entry `intent.captain.smash` | `E_INTENT_TELEGRAPH_MISSING` |
| hazard `tag:"acid"` | `E_HAZARD_TAG_UNKNOWN` |
| remove a normal object’s `reader` | `E_OBJECT_READER_MISSING` |

## 2. Closed vocabularies

| Category | Values |
|---|---|
| direct verbs | `n s e w`, `look/x`, `i`, `a`, `sh`, `b`, `t`, `u`, `g/get <id>`, `?`, `q` |
| multi-word forms | `north/south/east/west`, `go <direction>`, `look/examine <id>`, `inventory`, `attack [<enemy>]`, `shove <enemy>`, `brace`, `throw <item> [at <enemy>]`, `use <id>`, `take <id>`, `help`, `quit` |
| effects | exactly the 11 effect objects in §1 |
| hazard tags | `collapse`, `fire`, `drop`, `noise`, `cover`, `unstable_ground` |
| intent types | `strike`, `rush`, `smash`, `grab`, `guard` |

Hazard semantics: `collapse` damages a shoved target; `fire` damages on entry; `drop` moves target to `hazard`; `noise` ticks its declared clock; `cover` improves a brace outcome; `unstable_ground` makes a failed shove move the actor to `hazard`.

## 3. Engine contract

```python
Engine.apply(action: Action) -> list[Event]
```

This is the only mutation gateway. Parser, renderer, harness, content loader, and terminal loop may construct immutable `Action`/`Event` values only.

```python
Action = {
  "verb": "move|look|inventory|attack|shove|brace|throw|use|get|help|quit|retreat",
  "target_id": "ID|null",
  "direction": "north|south|east|west|null"
}

Event = {
  "type": "ID",
  "key": "event.key",
  "fact_slots": {"slot_name": "string|int|bool"},
  "numbers": {"roll": 1, "total": 1, "margin": 0, "damage": 0},
  "effects": ["closed effect objects"]
}
```

`DelveState` contains: pack ID, seed, RNG, player HP/max HP/AC/stats/zone, current room, inventory, present objects, flags, known clue IDs, known fact IDs, clock values, enemy HP/zone/current intent/index, terminal state, turn number, and run-local bank-memory.

Use one `random.Random(seed)` created at run creation. No global random calls.

| Resolution | RNG draws |
|---|---:|
| look, inventory, get, use, throw, shove, brace, move, retreat, help, quit | 0 |
| player attack | exactly 2: d20, then damage die; consume damage die even on a miss |
| active enemy damaging intent | exactly 2: d20, then damage die |
| intent selection, clocks, hazards, bank selection | 0 |

Reuse current stat feel: fighter `24 HP/AC16/+5/d10+3`; rogue `18/AC14/+5/d8+3`; wizard `14/AC12/+5/d10+2`; goblin `12/AC13/+4/d6+2`; captain `18/AC14/+5/d8+2`; skeleton `11/AC12/+3/d6+1`. Hit formula is current combat behavior: natural 20 hits; natural 1 misses; otherwise `d20 + attack_bonus >= AC`; damage is `max(1, die + bonus)`.

Enemy intent is declared on encounter entry and after every resolved hostile intent. It is selected by deterministic cycle index, never random. An enemy cannot deal damage unless its identical intent was visible in the prior rendered frame.

| Action \ intent | strike | rush | smash | grab | guard |
|---|---|---|---|---|---|
| attack | normal hit; intent resolves | normal hit; rush resolves | normal hit; smash resolves | normal hit; grab resolves | hit uses enemy AC+2 |
| shove | move foe `far`; strike misses | turn aside; foe `far` | if doorway, send foe to hazard | break grab, foe `far` | no move; guard remains |
| brace | halve damage | cancel push | negate damage | resist grab | wasted |
| throw | declared throwable interrupts | interrupts | interrupts if target doorway | distracts; grab fails | strips guard |
| use | item effect; intent resolves | item effect; intent resolves | item effect; intent resolves | item effect; intent resolves | item effect; intent resolves |
| retreat | invalid at `near` | valid from doorway; tick clock | valid from doorway; tick clock | invalid while grabbed | valid from doorway; tick clock |

`attack` is deliberately not dominant: it neither changes enemy position nor cancels declared danger. `shove`, `brace`, and `throw` must each produce a different state/output projection in their declared counter situation.

Movement puts the player in `doorway` on entry to an occupied room, declares intent, and causes no immediate enemy attack. Retreat moves to the selected open exit only from `doorway`; it ticks the pack-declared retreat clock source.

Clocks tick only from declared `tick_sources` or `tick_clock` effects. On crossing thresholds, execute threshold effects once in ascending order. Death always produces `terminal.death`; victory requires a validated victory terminal.

## 4. Terminal and render contract

Top-of-turn exploration:

```text
MOSSY ENTRY [near]  HP 24/24  PATROL [##..]  Exits: E
Rain taps the cracked stone. Bell [near]; chart [far]; dome [doorway].
> 
```

Top-of-turn combat:

```text
HOLLOW VAULT [doorway]  HP 17/24  PATROL [###.]  Exits: W
Hobgoblin Captain 18/18 HP [doorway] — SMASH: brace to negate; shove at doorway to drop the dome.
Hazard: COLLAPSE [hazard].  Objects: brass ring [near].
> 
```

Every hit/miss receives its own banked line and margin: `Your blade skids off the pauldron (miss by 3).` Never collapse combat into generic “you attack.”

```text
HELP — n/s/e/w move; x <thing> read; i inventory; a attack; sh <enemy> shove;
b brace; t <item> throw; u <item> use; g <item> get; q quit.
Enemy intent is shown before it resolves. Use zones, hazards, and exits.
```

```text
YOU DIED — The Captain's SMASH broke through because you attacked from the doorway.
Retry hint: brace the declared smash, or shove him beneath the collapse.
[r]etry or [q]uit
```

```text
VAULT CLEARED — You read the route, dropped the dome, and broke the Captain's guard.
The bell, chart, and dome now agree about what happened here.
[r]etry or [q]uit
```

Bank selection is deterministic. Eligible variants match the event’s declared fact slots. Select by SHA-256 of `seed|event_key|canonical_fact_slots`; exclude previously emitted variant IDs for that same `event_key|canonical_fact_slots` memory key. If exhausted, clear only that key’s memory and repeat. If no eligible variant exists, render `fallback`. Fallback is mandatory and nonempty.

Performance test: replay 100 fixed actions through actual `delve.__main__.main` input/stdout seams; record `perf_counter_ns()` around parse → `Engine.apply` → render, excluding process launch. Require p95 `<100 ms`, zero network calls, and byte-identical output for the same seed/actions.

## 5. M1 slice content brief

Five rooms: `mossy_entry` (goblin and brass ring), `collapsed_observatory` (collapse hazard), `chart_chamber` (clue room), `mira_gallery`, and `hollow_vault` (captain).

Payoff fact: `captain_route`. It becomes known only after three independent clues:

1. `u brass_ring` in Mira’s gallery: Mira says the captain always braces in the vault doorway.
2. `x star_chart`: the chart aligns the old dome fracture over that doorway.
3. `x collapsed_dome` or `x clapperless_bell`: the bell was silenced because the captain feared the falling stone.

Known fact enables the vault’s shove-to-collapse payoff; it is not a trivia answer. Gallery entry must state that Mira is present and wants the brass ring.

| Existing object | Reader result |
|---|---|
| clapperless bell | clue about the silenced warning |
| stone compass | shows the vault/dome alignment |
| star chart | second route clue |
| clay cup | takeable throwable; interrupts `grab` |
| silver leaf | throwable distraction; interrupts `guard` |
| offering bowl | `use` restores 2 HP once |
| brass nameplate | identifies Mira and her ring request |

Target first run: 8–14 minutes, 25–45 input calls. Bank covers at least: `room.enter`, `room.return`, `object.read`, `item.get`, `item.use`, `enemy.intent`, `attack.hit`, `attack.miss`, `shove.success`, `shove.fail`, `brace.success`, `throw.interrupt`, `hazard.trigger`, `clock.tick`, `clock.threshold`, `clue.reveal`, `fact.payoff`, `terminal.victory`, `terminal.death`.


## 6. Amendment 1 (Ivy, 2026-09-29): pickup semantics, found by the content unit

The M1.2 schema had no link between a room `Object` and an inventory `Item`, so `get` was undefined. Binding rules:

- `Object` gains an OPTIONAL field `item_id` (an `Item` id). An object with `item_id` is *takeable*; it still needs a `reader` (its look-reader) or `atmosphere_only`.
- `get <object_id>` (or `g`/`take`): allowed only if the object is present in the current room AND no living enemy is in the room (otherwise event key `get.blocked`, fact slot `enemy_name`, no state change). On success: the item id is appended to `inventory`, the object is removed from that room's `present_objects`, event key `item.get` with slot `item_name`. Getting an object that is not takeable emits `get.not_takeable`.
- `use <item_id>`: requires the item in inventory; fires the item's `reader` if its `on` is `use` and its `when_room_id`/`when_flag_id` conditions hold; else event `use.nothing`. `throw <item_id>`: requires the item in inventory and a living enemy with a declared intent; fires the item reader when `on` is `throw`.
- `look <object_id>` fires the object's `reader` when `on` is `look` and its conditions hold (present in current room); readers with `when_flag_id` unmet emit the same object's `object.read` fallback event (never silence).
- Enemies drop nothing in M1. The engine sets the reserved flag `__player_hp_zero` when player HP reaches 0 (the only reserved flag).
- Validator additions: `item_id` must reference an existing item (E_ITEM_UNKNOWN); an item may be referenced by at most one object (E_ITEM_DUPLICATE_SOURCE); new bank keys required for `get.blocked`, `get.not_takeable`, `use.nothing` (E_BANK_FALLBACK_MISSING if absent) -- content units add them.

## 7. Amendment 2 (Ivy, 2026-09-29): engine event catalog and clock-threshold rule

Every `Event` the engine emits has `type`, `key` (a bank key), `fact_slots`, `numbers`, `effects` (as spec section 3). The ENGINE-STRUCTURAL keys (the bank of any shipped pack must contain each with a nonempty fallback; a later unit adds the validator check E_BANK_STRUCTURAL_MISSING):

| Key | Emitted when | fact_slots |
|---|---|---|
| room.enter | first entry to a room | room_name |
| room.return | re-entry to a visited room | room_name |
| (room.description_key) | after room.enter/return and on `look` with no target | room_name |
| move.blocked | move attempted while a living enemy is in the room (use retreat) | enemy_name |
| move.no_exit | no exit that way (or gate denied: then the gate's denial_event_key) | direction |
| target.unknown | look/get/use/throw named an id not present/held | target |
| object.read | `look <object>` whose reader conditions are unmet, or objects read with no reader text | object_name |
| get.blocked / get.not_takeable / item.get / use.nothing | per Amendment 1 | as Amendment 1 |
| clue.reveal | generic line if a clue's own event_key is absent (normally the clue's event_key is emitted) | clue_id |
| fact.payoff | when all clue_ids of a payoff fact are known: emit once, then run payoff_effects | fact_label |
| clock.tick | a clock advanced | clock_label, value, max |
| clock.threshold.<clock_id>.<at> | a threshold crossed, if that key exists in the bank; else `clock.threshold` (slots clock_label, at) | clock_label, at |
| enemy.intent | reserved for generic intent declaration fallback; normally the intent's telegraph_key is emitted | enemy_name |
| attack.hit / attack.miss / shove.success / shove.fail / brace.success / brace.wasted / throw.interrupt / hazard.trigger | combat (M1.5+) | per combat unit |
| help | `?`/help | none |
| terminal.victory / terminal.death / terminal.retry | terminals | cause (death) |

Order within one `apply()`: (1) validate action, (2) player action resolution events, (3) effect events (in effect order), (4) clock tick(s) and threshold events (ascending), (5) fact payoff check, (6) enemy intent declaration/resolution (M1.5), (7) terminal check. `apply()` returns the whole ordered list and appends it to `state.event_log`. A blocked or invalid action changes no state, draws no RNG, ticks no clock, and still emits exactly one explanatory event. The `move` tick source ticks once per SUCCESSFUL move; `retreat` ticks its own source.

## 8. Amendment 3 (Ivy, 2026-09-29): combat round semantics, RNG accounting, invariants clarified

Clarifications (they override any looser reading of sections 3-4):

1. **event_log is not game state for the "invalid action changes nothing" invariant.** A blocked/invalid action leaves `snapshot()` identical EXCEPT for the appended explanatory event in `event_log`; tests compare snapshots with `event_log` and `turn` excluded... `turn` does NOT advance on an invalid action.
2. **Round structure** (only while a living enemy is in the player's room): player action resolves -> (if the enemy is alive and its declared intent was not cancelled/interrupted/negated per the table) the enemy's declared intent resolves -> the enemy advances `intent_index` and DECLARES its next intent (emit its telegraph_key event) -> terminal check -> control returns to the player. Declared intent is visible before it resolves: the telegraph of the intent that will resolve next is always emitted at the end of the previous round (or on room entry).
3. **Player attack**: exactly 2 RNG draws always (d20, then damage die, even on a miss): natural 20 hits, natural 1 misses, else `d20 + attack_bonus >= AC` (AC+2 if the enemy's current intent is `guard`); damage `max(1, die + damage_bonus)`. Margin = total - AC (negative on miss) for `margin` slot (`miss by {{margin}}` uses abs).
4. **Enemy intent resolution** (when it resolves): exactly 2 RNG draws (d20 vs player AC with the same nat-20/nat-1 rule, then damage die) ALWAYS taken when an intent resolves, even if brace later negates/halves it (stream stability). A cancelled/interrupted intent takes 0 draws. On a hit: damage = `max(1, die + damage_bonus) + intent damage effect amount`, then modified by the player's counter: brace vs `strike` = floor(damage/2); brace vs `smash` = 0 (negate); brace vs `grab` = 0 (resist); brace vs `rush` = intent cancelled (0 draws); brace vs `guard` = `brace.wasted`, guard persists this round. Intent effects other than damage (e.g. move_zone, set_flag) apply when the intent resolves and hits (or unconditionally if the intent has no damage effect).
5. **Shove**: 0 draws. vs strike/rush/grab: enemy moved to `far`, the intent is cancelled (0 draws) and event shove.success; vs guard: no move, intent persists (shove.fail); vs smash: succeeds ONLY if the room has a hazard whose trigger is `action: shove` and whose `requires_flag_id` (if any) is set (then the enemy moves to `hazard` zone, hazard effects execute (e.g. enemy damage), events hazard.trigger + shove.success, and the smash is cancelled); otherwise shove.fail and the smash resolves normally.
6. **Brace**: 0 draws, per point 4. **Throw**: `throw <item_id>` needs the item held and a living enemy with a declared intent; a tagged throwable (`throw_tags` contains `interrupt_<intent_type>` or `interrupt_any`) fires its reader effects (interrupt_intent) which cancels the current intent (0 draws; for `guard` it strips the guard: the enemy's guard bonus is removed this round) and the item is consumed; an untagged/mismatched throw emits `throw.fizzle`... (add to structural keys) consumes the item, and the intent resolves. **Use** in combat: item reader effects then the intent resolves. **Attack** does not cancel intents (the intent resolves after the hit unless the enemy died).
7. **Retreat**: `retreat <direction>` only from `doorway` with an open ungated exit; moves the player to that room, ticks the pack clock source `retreat` once (not `move`), the enemy's intent does NOT resolve, the enemy keeps its state; invalid from other zones or vs `grab` (`retreat.blocked`, no state change, add key).
8. **Enemy death**: hp <= 0 -> alive false, intent cleared, no drops; the room's living-enemy checks now pass (move/get allowed). Player death: hp <= 0 after any resolution -> flag `__player_hp_zero` set, terminal death event carries `cause` = the killing intent's enemy name and intent type.
9. New structural bank keys added by this amendment: `throw.fizzle`, `retreat.blocked`, `brace.wasted`, `intent.cancelled`. Content unit must add them with 4+ variants each.
