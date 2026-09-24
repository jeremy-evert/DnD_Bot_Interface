# D&D 0.4 — persistent room objects + LLM room dressing

Implement D&D 0.4 — Persistent room objects + LLM room dressing.

Scope discipline:

- Do **not** perform the 0.5 refactor yet.
- Do **not** expand the map yet.
- Do **not** add GUI, voice, agents, databases, or new frameworks.
- Preserve the deterministic-engine / creative-LLM boundary.
- Keep the standard-library-first approach.

Before coding, inspect the current main branch and existing tests.

Build:

1. persistent environmental room objects
2. factual LOOK output that exposes actual room contents
3. TAKE with no target listing takeable objects
4. deterministic aliases for obvious shorthand such as ring -> goblin's brass ring
5. structured LLM room-object suggestions on first meaningful room entry
6. strict Python validation before LLM suggestions enter world state
7. persistence when leaving/re-entering rooms
8. reduced routine combat narration, reserving LLM narration for higher-value moments

The LLM may suggest mundane flavor objects only. It must not create mechanical bonuses, healing, spells, exits, enemies, rewards, or altered game facts.

Once Python accepts an LLM-created object, that object becomes persistent game state.

Core rule:

> The LLM may invent things, but once invented, Python has to make them real.

Add deterministic tests for all new boundaries. Mock LLM calls in tests. LLM failure or timeout must never block play.

Run the full test suite and a scripted smoke test. Leave the working tree clean, then summarize what changed and any design pressure that should inform the later 0.5 refactor.
