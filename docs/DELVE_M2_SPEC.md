<!-- Binding M2 plan and amendments for Fast Delve M2 'The Dramatic Delve' (Terra plan terra-m2-dramatic-delve-01, approved by Ivy 2026-09-30). Amendments 5-12 are binding on all M2 units. Numeric acceptance and process/review budget sections are binding on Ivy's dispatches. -->
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
