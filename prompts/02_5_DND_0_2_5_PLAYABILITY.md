# D&D 0.2.5 — human playtest polish

Use the human playtest of D&D 0.2 to build a very small D&D 0.2.5 playability-polish milestone.

Do NOT add an LLM yet.

The playtest exposed these specific issues:

1. After an enemy dies, room descriptions still describe that enemy as alive.
   Room/look text must reflect persistent game state.

2. Direction input should accept natural aliases:
   north/n, south/s, east/e, west/w.

3. Defeated enemies should support a tiny loot system.
   Keep it extremely small.
   The first goblin should leave behind at least one takeable item.
   It is fine for most loot to be simple inventory flavor, but at least one
   item in the adventure should have a small mechanical effect.

4. Define the combat rule for invalid/non-usable actions.
   For example, attempting to use a potion when none exists should NOT consume
   the player's turn.
   Make this behavior explicit and test it.

5. Preserve HP, inventory, defeated enemies, removed items, and room state as
   the player moves around the dungeon.

6. Improve command handling only enough to make the terminal game pleasant.
   Do not build a general parser.

7. Keep deterministic game rules separated from terminal I/O.

8. Expand deterministic tests for all changed behavior.

Do not add:
- AI
- LLM
- agents
- GUI
- voice
- database
- unnecessary dependencies

Run all unit tests and a scripted full-adventure smoke test.

Leave the repository in a clean working state.
