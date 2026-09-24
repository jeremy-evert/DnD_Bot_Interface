# D&D 0.2 — The Mossy Delve

> Historical status: **reconstructed** from the implemented 0.2 milestone because the original prompt was not stored in the repository.

Turn the combat prototype into the smallest connected dungeon adventure.

Requirements:

- ask for the hero's name
- choose Fighter, Rogue, or Wizard with meaningfully different fixed stats
- three connected rooms
- movement between rooms
- LOOK and STATUS
- first goblin encounter
- healing potion in the middle room
- tougher final Hobgoblin Captain encounter
- HP and inventory persist between rooms
- defeating the final encounter wins
- player death ends the adventure
- deterministic game rules remain separate from terminal I/O
- deterministic tests
- standard library only

Do not add:

- AI or LLM
- agents
- GUI
- voice
- database

Success condition:

`python3 -m dnd_combat` lets a player choose a character, explore three rooms, fight, use an item, and either die or complete the dungeon.
