# DnD_Bot_Interface agent instructions

## Project purpose

Build a small, playable D&D-style terminal adventure that can gradually become an AI-assisted role-playing game without surrendering rules or world state to the LLM.

## Non-negotiable architecture rule

**Python is authoritative. The LLM is creative, not sovereign.**

Python owns:
- dice and combat resolution
- HP and death
- movement and exits
- inventory
- room/object persistence
- mechanical loot and effects
- victory conditions
- validation of anything suggested by an LLM

The LLM may:
- narrate selected important events
- suggest mundane scenery through a structured, validated boundary
- eventually play NPC dialogue
- eventually interpret unusual player intent

The LLM must never directly mutate game state.

## Working style

- Keep the standard-library-first approach unless a dependency clearly earns its keep.
- Prefer small milestones over framework rewrites.
- Preserve deterministic tests.
- Mock LLM calls in tests.
- LLM timeout/failure must never block ordinary play.
- Do not expand later milestones early.
- Human playtests are design evidence. Preserve the behavior they reveal rather than polishing around it blindly.

## Prompt archive

Milestone prompts live in `prompts/`.

`prompts/CURRENT` names the mission that `scripts/hanna` should launch by default.

Historical prompt files labeled **reconstructed** preserve intent from the actual commit/chat history when the original wording was not stored verbatim.

## Current sequence

1. D&D 0.4 persistent room objects — complete and human-playtested.
2. D&D 0.5 refactor checkpoint — complete and green.
3. D&D 0.6 map expansion — current mission.

## Before editing

1. Read the current mission prompt.
2. Inspect the current repository and tests.
3. Keep the work inside that mission's scope.
4. Run the full deterministic suite plus relevant smoke tests.
5. Leave the working tree clean.
