<!-- Binding M2 plan and amendments for Fast Delve M2 'The Dramatic Delve' (Terra plan terra-m2-dramatic-delve-01, approved by Ivy 2026-09-30). Amendments 5-12 are binding on all M2 units. Numeric acceptance and process/review budget sections are binding on Ivy's dispatches. The full unit list lives in evidence/dossiers/terra_m2.md. -->
# M2 plan: The Dramatic Delve

`plan_id`: `terra-m2-dramatic-delve-01`
`role`: Terra / Penny the Planner, read-only
`target`: `/mnt/nora/git/worktrees/ivy-dnd-delve`, current `ivy/fast-delve-m1@fb06374`
`classification`: local-only experimental game work; Python-authoritative; no live model, network, accounts, student data, or deployment.

## Vision and the 15-minute experience

M2 turns Fast Delve from a readable combat puzzle into a compact dramatic-systems game: the Rogue makes monsters choose the wrong victim, the Wizard makes a room catastrophically different, and the Fighter decides where a crowd is allowed to exist. In fifteen minutes, a player sees a hungry cave drake, two goblins, oil, bait, a failing gate, and clear enemy intentions; they choose a costly plan rather than a counter-table answer; the room visibly changes; and Mira remembers the concrete consequence. “Lead the drake to eat the goblins” and “cast Fireball” become deterministic engine actions with visible prices—not parser wishes or high-damage attacks.

The current evidence makes this necessary. The supplied 500-seed simulation has smart-policy wins of Fighter 90.4%, Rogue 73.6%, Wizard 57.2%, while the Wizard dies to the tutorial goblin in 42.8%; attack-only wins 0% but the present brace/shove table remains solved. The current engine’s `_living_enemy()` selects the first live enemy, so it cannot yet express monster ecology. The supplied pilot README records M1 iteration 3 as 3/4 wins; the requested later M1.14 report of three golem deaths should be reproduced and preserved as a pre-promotion measurement, not silently merged into the older receipt.

## Codebase decision

Build on `delve/`, not `dnd_combat/`.

`dnd_combat` remains the frozen 0.6 reference. Its hard-coded encounter loop and Genny’s old Magic Missile implementation are useful design evidence, but are the wrong home for pack-defined multi-actor rounds, materials, actor movement, and content validation. `delve` already owns the required architecture: pack → `DelveState` → `Engine.apply()` → events → banked renderer, and the v2 harness already replays `delve.__main__.main`.

Genny’s 0.6 work maps cleanly:

| Genny contribution | M2 disposition |
|---|---|
| Magic Missile: auto-hit `2d4`, three charges per encounter | Port the rule as the Wizard’s reliable `m <enemy>` class action in `delve`; it remains materially different from Fireball. |
| Print deterministic text before model narration | Make banked deterministic event text the only M2 text path. It renders immediately after `Engine.apply()`. |
| Prefetch/model narration | Do not enable it in M2. Reserve a later optional `GarnishQueue` seam keyed by immutable event hash. It may append already-ready prose after deterministic text, may never delay a frame, mutate state, replace text, or change a replay. Turning it off must produce a fully playable identical mechanical run. |

M2 has no live model dependency and no prefetch worker. The seam is specified now so it is not retrofitted into the mutation path later.

## Concrete design

### Class kits

Generic actions remain available to everyone: move, step zone, attack, brace, shove, throw, use, retreat. Generic `brace` now halves a hit; it never fully negates a `smash`. Full prevention is class-resource territory.

Base tuning target:

| Class | HP | AC | basic attack | identity |
|---|---:|---:|---|---|
| Fighter | 22 | 15 | d8+3 | controls crowd and chokepoints |
| Rogue | 19 | 14 | d8+3 | relocates danger and prepares terrain |
| Wizard | 18 | 13 | staff d4+1 | reliable magic, protection, one irreversible room change |

| Class | Ability / key | Cost and limit | Exact deterministic effect | Witness situation |
|---|---|---|---|---|
| Fighter | Hold Door / `h` | 1 Momentum; once per encounter; requires doorway | Stance for next two hostile beats: only one doorway attacker may resolve; reduce that attacker’s damage by 3; player cannot retreat; each resolved hit adds 1 `strain`; at strain 2 the held support becomes releasable. | Two-plus enemies or a drake route crossing a doorway. |
| Fighter | Cleave / `c` | 2 Momentum | One attack roll and damage roll per up to two enemies in the player’s zone; does not cancel their intents. | Two wounded goblins clustered in doorway/near. |
| Fighter | Guardbreak / `k <enemy>` | 1 Momentum; cooldown 1 hostile beat; target telegraphs `guard` | Cancel guard; apply `opened` to target until the Fighter’s next attack attempt; that attack uses AC −3; no damage from Guardbreak. | Guarded captain/goblin leader. |
| Rogue | Lure / `l <bait> at <actor> to <zone>` | 1 Trick; once per room; consumes authored bait | Apply `scented` to named actor, emit the bait signal, and move Rogue one adjacent legal zone in the same player beat. | Drake can reach scented goblin before player; attack cannot buy the safe reposition. |
| Rogue | Slip / `z` | 1 Trick; cooldown 2 hostile beats | Against declared strike/rush/grab, move Rogue to an adjacent legal zone and cancel that actor’s current intent. | Low HP, then retreat/rig/object interaction is available. |
| Rogue | Rig / `r <object>` | 1 Trick; once per object | Add `rigged` to a visible `heavy` or `fragile` object; later impact, shove, or heat uses the ordinary material rule. | A support/gate is present and will be crossed by enemies. |
| Wizard | Magic Missile / `m <enemy>` | 3 charges per encounter; no cooldown | Auto-hit named enemy for `2d4`; exactly two seeded RNG draws; does not cancel intent. | One dangerous target is near defeat or must be removed before a second beat. |
| Wizard | Ward / `w` | 1 Ward, two per encounter; cooldown 1 hostile beat | Set a six-point shield against the next one declared hostile intent; leftover shield expires after that intent. It does not stack with brace. | Tutorial goblin or another telegraphed lethal hit. |
| Wizard | Fireball / `f <zone>` then confirm | one Spark per delve; confirmation required | Deal fixed 8 fire damage to all actors in target zone; send `heat` and `sound`; destroy affected `flammable`/`fragile` objects; ignite `oiled` material; interrupt only actors killed or displaced by resulting rules. | Two-plus enemies in an oiled zone, with visible desirable burn losses. |

Fighter Momentum starts at 1 each encounter and gains one from a successful brace, shove, or kill, capped at 3. Rogue Tricks start at 2 in each room and refresh only upon entering a room while no actor targets the Rogue. Wizard resources are intentionally unlike the other classes: three reliable missiles per encounter, two defensive Wards, and one delve-wide Fireball.

Ability data is pack data, not Python branching by ability ID:

```json
{
  "id": "fireball",
  "class_id": "wizard",
  "command": {"verb": "class", "key": "f", "target_kind": "zone", "confirm": true},
  "resource": {"id": "spark", "scope": "delve", "cost": 1, "maximum": 1},
  "requires": {"visible_zone": true},
  "effects": [
    {"type": "damage_selector", "selector": "actors_in_zone", "amount": 8},
    {"type": "signal", "kind": "heat", "selector": "zone"},
    {"type": "signal", "kind": "sound", "selector": "zone"}
  ],
  "event_key": "ability.wizard.fireball",
  "memory_tags": ["fire", "force"]
}
```

The validator accepts only a closed ability catalog and closed selectors. The model never authors damage, target sets, effects, or success.

### Material layer

Visible tags are finite and status-rendered: `flammable`, `wet`, `oiled`, `burning`, `smoke`, `fragile`, `heavy`, `loud`, `bright`, `edible`, `scented`, `cover`, `hidden`, `rigged`.

Tags attach only to authored objects, zones, or actors. `loud` is an event tag, not a permanent atmosphere adjective. A tag has no meaning outside these rules:

| Rule | Trigger | Deterministic result |
|---|---|---|
| R1 oil flash | heat + `oiled` | consume oil; 4 fire damage to every actor in zone; `burning` for two beats |
| R2 ignition | heat + `flammable` | consume object; execute validated `on_burn` payload |
| R3 damp heat | heat + `wet` | remove wet; add smoke/cover for two beats |
| R4 fire spread | burning adjacent to authored flammable connection | ignite one connected zone next beat; once per zone |
| R5 extinguish | water + burning | remove burning; add wet and smoke for two beats |
| R6 break | impact + fragile | consume object; execute its validated contents/support payload |
| R7 drop | impact + rigged heavy | one 10-damage crush to landing zone; interrupt occupants; create rubble cover; consume support |
| R8 sound | sound/loud | record source zone; tick declared patrol clock once; wake listening actor |
| R9 appetite | edible/scented visible to hungry actor | actor telegraphs hunt toward highest-priority legal target |
| R10 feeding | hungry predator shares zone with edible enemy faction | declared predator attack resolves as fixed actor-vs-actor damage |
| R11 fear | bright visible to light-fearing actor | actor telegraphs flee to ranked safe destination |
| R12 sight | smoke/cover crosses sight line | sight-dependent ranged intent misses; scent/appetite still works |

Rules run exactly in order R5 → R6 → R1/R2 → R4 → R3 → R8 → R9/R11. Each rule has `(beat, source_id, target_id)` fuel; no tuple fires twice. At most three reaction steps occur in one `apply()`; unspent scheduled reactions carry to the next beat. That makes every chain terminating, inspectable, and readable.

### Multi-enemy rooms and ecology

This is the prerequisite, not content polish.

- Replace first-live-enemy semantics with `living_actors(room_id)` sorted by stable actor ID.
- Actions name one target where required; selectors snapshot their sorted target IDs before effects execute.
- Room status lists every living actor with HP, zone, declared intent, declared target, and salient tags.
- Every actor has `faction`, `initiative`, `appetite`, `fears`, `morale`, `aggro`, `state`, and a declared intent snapshot.
- On each successful player beat: resolve player action → material reactions → previously telegraphed actor intents in `(initiative desc, actor_id)` order → timed hazards → terminal check → select and emit next intents. No actor damages any target without that exact action/target being printed in the preceding frame.
- Actor movement uses shortest valid authored exit path; ties are `(path length, room id, actor id)`. An actor moves at most one room per beat.
- Actor-vs-actor attacks use fixed damage: drake bite 8, goblin strike 2. This preserves simple RNG accounting and makes ecology forecastable.
- If a target becomes invalid, the actor cancels, prints why, and declares again; it may not silently retarget and attack.

Kiln drake priority: finish declared bite → flee announced crush → pursue scented living prey → consume loose edible bait → retaliate against last attacker → digest two beats after feeding → sleep/sated.

Banquet goblin priority: flee drake in zone → guard assigned food/exit → strike reachable intruder → return to post.

### Vertical slice: “The Sundered Menagerie”

Four rooms, one 12–15 minute run:

| Room | Cast and authored material | Purpose |
|---|---|---|
| Broken Gate | one 6-HP goblin, wet awning, oil lamp, heavy awning support | nonlethal two-beat tutorial for Ward, Rig, or Hold Door; Wizard cannot die here |
| Salt Larder | roast (edible; can heal 4 if consumed), oil flask, feeding ledger, tooth-marked bone | collect bait and two drake clues; choose healing versus lure resource |
| Sundered Menagerie | Goblin Hook and Goblin Slinger, young cave drake behind beast-door, oiled supper table, silk map, fragile chain, heavy split arch, doorway baffle | selling encounter; each class has a visible distinct route and a real price |
| Mira’s Balcony | Mira, brass case, exit | concrete reaction, ending, chronicle; no combat |

Three clues explain the drake route: salted aprons, tooth-marked bone, and Mira’s feeding ledger. They unlock an exact forecast, never permission for the rules to work. The victory predicate is outcome-based: reach Mira’s Balcony with the brass case and either neutralize the goblin guard pair, bypass them, or create an open route. It must not require a fact, Fireball, Lure, or a kill.

| Class | Route one | Route two |
|---|---|---|
| Fighter | Hold the arch while goblins funnel; build Momentum; Cleave clustered pair | Rig/release split arch after drake crosses; use Guardbreak to pass guarded Hook |
| Rogue | Lure roast onto Hook and step away; drake eats goblins and digests | Rig chain/arch, Slip past a declared rush, drop support to make cover and escape |
| Wizard | Fireball the oiled supper zone: kill/break pair, burn silk map, wake drake | Ward tutorial/first lethal beat, Magic Missile the weakened guard, then use ordinary environment route after the drake is fed or separated |

At least two route-restricted policies per class must reach the exit at ≥60% over 2,000 seeds. “Force” is permitted, but must not be the only viable route.

### Spectacle, chronicle, and Mira

Set-piece bank entries carry `chain_id`, `beat`, `requires_event_keys`, `minimum_effect`, and a deterministic fallback. Maximum one set piece per encounter; routine attacks remain terse.

```text
>>> CHAIN: SCENT → HUNT → FEED <<<
You hook the roast beneath the Hook’s collar and step away.
The beast-door bends inward.
The Hook stops laughing first.
The drake eats the apron, the goblin, and the argument.
AFTERMATH: the drake digests. The supper table is gone.
```

```text
>>> FIREBALL: OIL → FIRE → FLIGHT <<<
The table goes white.
The silk map rises in black pieces.
The goblins break toward the only thing hungrier than fire.
AFTERMATH: FIRE [far], 3 damage next beat; drake awake.
```

`ChronicleBuilder(event_log)` is pure Python, consumes no RNG, and emits at most one cited line from each role: entry, Mira interaction, signature act, sacrifice, resolution, ending. Every line includes compact event citations in test mode and is omitted if its required events are absent.

Mira memory hooks are bounded event tags, never points:

- `fire`: Fireball or ignition caused material loss.
- `lure`: predator hunted an actor due to player bait.
- `hold`: Fighter stance prevented a hostile beat.
- `cunning`: Rig/Slip materially changed the exit.
- `mercy`: player bypassed or spared a surviving actor.
- `force`: crush/Cleave/Guardbreak materially resolved a route.

Mira may react to the first decisive tag in each category. Repeating an action cannot farm another memory. There is no Legend meter.

## Binding spec amendments

### Amendment 5 — M2 pack and actor schema

M2 packs use `schema_version: 2`. M1 version-1 packs remain runnable unchanged. A version-2 actor has stable `id`, `room_id`, `zone`, stats, faction, initiative, state, intent definitions, appetite/fear/aggro profile, and optional inactive state. `Engine` must reject a v2 pack that uses a v1-only one-enemy assumption, an unknown selector, unknown tag, unknown resource, unknown chain field, or missing bank coverage.

### Amendment 6 — multi-actor turn contract

`_living_enemy()` may not be used for v2 resolution. `living_actors(room)` and all target selectors return stable sorted snapshots. Player actions, actor intents, effects, rendering, movement blocking, terminal checks, and detectors must use these snapshots. A target invalidated before its intent resolves causes an explicit cancellation event and a later declaration, never implicit retargeting.

### Amendment 7 — material and reaction contract

The fourteen tags and twelve rules above are the complete M2 vocabulary. `signal` is limited to `heat`, `water`, `impact`, and `sound`; selector and tag fields are validated data, not expressions. Rule fuel, fixed order, three-step reaction ceiling, and consumption semantics are mandatory. A chain may not recursively create unbounded reactions.

### Amendment 8 — class-action contract

`Action` gains closed `class` and `step` verbs plus typed target fields. Class action records define class, key, resources, preconditions, cooldown, effects, and event key. `Engine.apply()` alone verifies eligibility, spends resource, confirms Fireball, and applies effects. Unavailable class actions do not change RNG, turn, resources, clocks, or state.

### Amendment 9 — telegraph and RNG contract

Each actor’s next action, target, destination, and mechanical consequence is rendered before it resolves. Actor-vs-actor attacks use no RNG in M2. Magic Missile consumes exactly two `d4` draws. Player attacks retain two draws; Fireball, Ward, Lure, Rig, Hold, Cleave target selection, materials, and ecology add no undeclared randomness.

### Amendment 10 — outcomes rather than prescribed routes

A terminal may predicate only on authored outcome states, inventory, room, actor status, or flags resulting from completed actions. A terminal may not require `fact_known`, a particular class action, a route label, or a particular event key. Facts unlock forecasts and opportunities only.

### Amendment 11 — bank, chronicle, and detector seam

Every emitted event key and exact fact-slot set must be declared in the pack bank and in a generated engine-event manifest. `render_event`, `render_status`, `ChronicleBuilder`, simulation route classifier, and transcript detectors consume that same manifest. A pack validation receipt includes pack hash, bank-manifest hash, route-classifier version, and tag-rule version. Missing, renamed, or slot-incompatible keys fail load or measurement; content changes cannot yield an apparently clean but blind detector run.

### Amendment 12 — optional garnish

A future garnish receives an immutable copy of a completed event packet and event hash after bank text has rendered. It has no handle to `DelveState`, `Engine`, RNG, pack, parser, or terminal control flow. Its absence, timeout, exception, malformed output, or late result is ignored and produces no state or timing difference in the deterministic run.

## Acceptance boundaries

| Invariant | Production path | Enforcer | Failure modes | Write path | Discriminating assertion; wrong implementation |
|---|---|---|---|---|---|
| All actors are real actors | parser → `Engine.apply` → actor scheduler → state | `living_actors`, selector snapshot, scheduler | flat ecology, target drift, first-enemy bug | `delve/engine.py`, `delve/state.py`, `tests/test_delve_multi_actor.py` | Kill actor A before selector resolves; actor B still receives its preselected effect. Reject “loop effects through `_living_enemy()`.” |
| Damage is telegraphed | status renderer → player beat → intent resolver | declared-intent snapshot | surprise damage, unreadable chain | `delve/engine.py`, `delve/render.py`, tests | Every player or actor damage event cites a matching prior declared target/action. Reject “retarget drake and bite in one frame.” |
| Materials terminate and stay finite | `signal` → reaction queue → state/events | reaction fuel/order/ceiling | chain runaway, special-case solution | `delve/materials.py`, `delve/engine.py`, tests | 1,000 repeated signal fixtures stop in ≤3 reactions/beat and consumed oil never flashes twice. Reject “while reactions: process newly spawned fire forever.” |
| Class actions are real choices | parser → class resolver → resource state | `apply_class_action` | fantasy breach, one-trick class, hidden cost | `delve/engine.py`, `delve/commands.py`, tests | Fireball names burned objects before confirmation and spends Spark once only. Reject “Fireball is attack with +damage.” |
| Outcome does not prescribe route | pack → terminal validator → terminal check | `validate_terminal_outcomes` | single-route encounter | `delve/pack.py`, tests | Remove all facts and reach victory by bypass/neutralization route. Reject “victory requires `fact_known`.” |
| Bank text cannot blind mechanics or measurement | pack → manifest → engine events → renderer/detectors/chronicle | `validate_event_manifest` | detector blindness, invented chronicle | `delve/pack.py`, `delve/render.py`, `delve/measurement.py`, tests | Rename `ability.wizard.fireball` only in content; load/measurement fails. Reject “renderer falls back while classifier silently ignores the event.” |
| Chronicle is grounded | event log → pure ChronicleBuilder → renderer | `ChronicleBuilder` | false Mira memory, fabricated ending | `delve/chronicle.py`, tests | Generated sentence’s cited events exist and precede it in event log. Reject “choose flattering ending from class alone.” |
| Optional narration cannot affect play | event packet → bank render → optional garnish | immutable packet boundary | proposal authority leak, latency break | later `delve/garnish.py`, tests | Stub blocks/raises/mutates packet: state and deterministic stdout remain byte-identical. Reject “await model before next prompt.” |

## Process and review budget

Allocate at least 65% of Codex time to new engine/content construction, 20% to deterministic tests and simulation, and at most 15% to Sol review. T0 units receive deterministic tests, coordinator diff read, and one real-data seam check only. T1 receives exactly one Sol pass against its pre-written finite claim and threat model. T2 is limited to the shared schema and multi-actor contract; each gets no more than two adversarial passes.

A measured gate replaces expensive review wherever possible: real-engine policy simulation, content-manifest validation, and a cheap blind-golem vertical-slice run.

## Numeric acceptance

Run 2,000 seeds per `(class, policy, encounter)` cell, report raw denominator and 95% intervals.

- Wizard tutorial-goblin death: **below 10%**; the tutorial itself is nonlethal.
- Class-signature and search-policy full-slice win rates: each **75–90%**, with max-minus-min **≤10 percentage points**; no class strictly dominated in stats plus exclusive verbs.
- Attack-only full-slice win rate: **≤10%** for every class.
- Every class ability has a reachable visible witness state in which it is strictly better than attack: at least **+5 percentage points rollout win value** or **+3 expected exit HP**; restricted `without(ability)` loses **>2 points** in at least one intended encounter.
- Every class has at least two route-restricted approaches with **≥60%** win rate; best-minus-second-best route **≤25 points**.
- A memoryless telegraph table must not reach ≥95% of search-policy win rate while taking near-zero damage.
- No chain route may produce ≥99% win rate and ≥50% less damage than the next-best route.
- Actual entry-point p95 parse → apply → render latency remains **<100 ms**.

Blind golem play is a cheap existence/discovery check after the simulation gate: six runs, two per class, public prompts that mention only what help/status displays. It must show at least one non-attack route, no unexplained death, and correct causal retelling of one chain. It is not a frequency measure.

Jeremy’s test is a class-swap session: two 15-minute runs in different classes, counterbalanced when possible. Ask only: “What was the coolest thing you did?”, “What did you want to do but could not?”, “Did the class feel different?”, “Did you save an ability?”, and observe voluntary third-class choice. M2 does not claim success without one human saying a concrete non-attack consequence they caused.

## Cut list and risks

Do not build:

- a Legend meter;
- live LLM tactics, free-text tactic interpretation, or prefetch;
- a full Divinity/Noita material simulator;
- procedural monster spawning;
- a new mystery campaign, broad narration expansion, GUI, persistence, or web surface;
- victory predicates that demand the “correct” clue route;
- free full-negation brace or ID-specific throwable puzzles.

Main risks are shared-contract surgery, Fireball trivializing rooms, ecology becoming opaque, and simulation overfitting. The mitigations are v2 pack isolation, fixed reaction fuel, visible tags/forecasts, route-restricted policies, public deterministic fixtures, and the human class-swap gate.

## Genny decision and Ivy’s proposed first build

Genny should decide whether she accepts the M2 contract’s deliberate separation: Magic Missile is the reliable wizard workhorse, Fireball is the once-per-delve destructive set piece, and model narration is deferred optional garnish. She should also approve the exact “Fireball burns the silk map but not the brass case” consequence before content production.

Ivy should build first: **U1 schema/manifest, then U2 multi-actor scheduler**, before any class prose or Menagerie content. The first player-visible proof after that is the Rogue applying bait to Goblin Hook, stepping back, and watching a telegraphed drake eat him.
