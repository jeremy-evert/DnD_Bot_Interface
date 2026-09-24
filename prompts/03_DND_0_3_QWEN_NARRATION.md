# D&D 0.3 — optional local-LLM narration

Build D&D 0.3: optional local-LLM narration.

The deterministic game engine must remain the sole authority for all game state,
rules, dice, combat, inventory, movement, enemies, victory, and death.

Add an OPTIONAL narrator layer.

Requirements:

- The game must still work perfectly with no LLM server running.
- Use only the Python standard library if practical.
- Support an OpenAI-compatible local HTTP endpoint at:

    http://localhost:8080/v1/chat/completions

- Make the model configurable with an environment variable.
- Do not hardcode game logic into prompts.
- Do not allow the model to change game state.

Create a small narrator abstraction, for example:

    Narrator
    PlainNarrator
    LocalLLMNarrator

PlainNarrator should preserve the current deterministic text behavior.

LocalLLMNarrator should receive structured facts about a game event and return
a short atmospheric narration.

Narrate only important events initially:

- entering a room
- finding an item
- attack hit
- attack miss
- taking damage
- defeating an enemy
- player death
- victory

Keep narration short, around 1-3 sentences.

The prompt must explicitly tell the model:

- Do not invent game events.
- Do not change numbers.
- Do not create items, monsters, rooms, spells, rewards, or outcomes.
- Describe only the supplied facts.
- If uncertain, say less rather than inventing something.

If the local server fails, times out, or returns malformed output, immediately
fall back to PlainNarrator and continue the game.

Add deterministic tests for the narrator boundary without requiring a live LLM.

Do not add:
- agents
- smolagents
- GUI
- voice
- databases
- autonomous DM behavior

Run all tests and a smoke test.

Leave D&D 0.3 playable both with and without the local model.
