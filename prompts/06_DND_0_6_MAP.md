# D&D 0.6 — spice up the map

**Do not run this mission until D&D 0.5 is complete, green, and human-reviewed.**

Expand the current three-room proof into a small but interesting exploration map.

Target roughly 8–12 rooms, not a campaign.

The map should include:

- at least one meaningful branch
- at least one loop or alternate route
- an optional dead end or curiosity room
- several distinct room types
- persistent room objects
- at least one NPC/dialogue opportunity
- deterministic mechanical encounters
- some rooms where nothing attacks the player
- enough revisiting that memory and carried objects can matter

Preserve:

- Python authority over mechanics and state
- validated LLM room dressing
- clean command/world/LLM boundaries from the 0.5 refactor
- standard-library-first design
- deterministic tests and failure fallback

The map should create opportunities for:

- carrying odd objects between rooms
- NPCs reacting to persistent inventory
- revisiting rooms after state changes
- Qwen adding atmosphere without inventing mechanical truth

## Playtest evidence is part of 0.6

D&D 0.6 is an experiment, not merely a larger map.

A human playtest should leave durable evidence of what actually happened so later design work can distinguish "this sounded fun in planning" from "this was fun in play."

Add the smallest useful standard-library-first session recorder.

The recorder should capture enough evidence to reconstruct meaningful play, including:

- session identifier and timestamps
- player input
- resolved deterministic command/action when one exists
- room/location
- important deterministic outcomes and state changes
- dice/check/combat outcomes when relevant
- LLM request type when an LLM is used
- LLM response or structured proposal needed to understand the interaction
- whether an LLM proposal was accepted, rejected, or fell back
- useful latency/fallback diagnostics
- unsupported or unrecognized player attempts

Do not log secrets, credentials, environment values, private keys, or unrelated machine information.

Prefer an append-only, inspectable format such as JSON Lines. Runtime session logs should remain local and should not accidentally become committed campaign data.

Provide a small human-readable session report command or script so a playtest can be reviewed without manually reading raw JSON.

The recorder must not become a database project, analytics framework, GUI, or telemetry service.

## Steve / Mac laboratory mode

Steve may be used as the discovery machine while the project is learning what is fun.

The game should remain able to use an OpenAI-compatible narrator endpoint through `DND_LLM_ENDPOINT`.

For Steve, a local MLX/OpenAI-compatible endpoint may be used when available, but:

- local inference must remain optional
- narrator failure must never stop deterministic play
- remote/local model configuration must stay outside game mechanics
- routine deterministic actions should not require an LLM call
- higher-value narration, NPC dialogue, and future unusual-intent experiments may use a more generous creative budget than routine combat text

The authority boundary does not change:

> The LLM may be more creative, but Python still decides what becomes true.

## Human playtest questions

The resulting playtest evidence should help answer:

- What made the player curious?
- What decision required actual thought?
- What surprised the player?
- What earlier room/object/event did the player remember and reuse?
- Did the player deliberately carry something weird?
- Did an NPC or room react to prior state?
- Where did narration feel slow?
- Where did the world feel fake?
- What did the player try that the interface could not understand?
- Did the player want to keep playing after the nominal objective was complete?

Do not make the map huge. The goal is to prove exploration, continuity, reactive world behavior, and useful playtest evidence.
