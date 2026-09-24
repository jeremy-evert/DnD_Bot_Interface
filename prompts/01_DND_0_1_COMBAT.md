# D&D 0.1 — smallest playable combat

> Historical status: **reconstructed** from the implemented 0.1 milestone because the original prompt was not stored in the repository.

Build the smallest terminal D&D-style combat game that proves the core rules work.

Requirements:

- one human hero
- one goblin
- HP
- armor class
- initiative
- d20 attack rolls
- damage rolls
- alternating turns
- one attack action
- victory when the goblin reaches 0 HP
- death when the hero reaches 0 HP
- terminal output that makes the state understandable
- deterministic tests

Keep combat rules separate from terminal input/output.

Do not add:

- AI or LLMs
- agents
- GUI
- voice
- maps
- databases
- external dependencies

Success condition:

From the repository root, one command starts a fight and the player eventually wins or dies. Tests can force deterministic rolls.
