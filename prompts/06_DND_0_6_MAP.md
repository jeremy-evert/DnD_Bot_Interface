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

Do not make the map huge. The goal is to prove exploration, continuity, and reactive world behavior.
