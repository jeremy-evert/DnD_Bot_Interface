# D&D 0.5 — refactor checkpoint

D&D 0.4 has now been human-playtested.

Proceed with the 0.5 refactor checkpoint.

This is a behavior-preserving refactor, not a feature sprint.

## Human playtest pressure

1. Command handling needs a dedicated boundary.

   `ring` works as an alias today, but `potion` and `healing` do not.
   Build a small reusable deterministic object/command matching mechanism
   instead of accumulating hardcoded aliases.

2. Anything visibly described as an interactable room noun should be represented
   in world state where practical.

   Example: `broken crates` should not exist only in prose while TAKE/LOOK
   know nothing about them.

3. Structured room-object generation exposed both malformed JSON and timeout
   fallback paths. Model transport/parsing concerns should not leak through the
   game/world classes.

## Separate these responsibilities clearly

- world state / persistent objects
- game rules
- player command handling
- terminal presentation
- LLM adapter / structured LLM parsing

The LLM adapter should own:

- request/response handling
- timeouts
- structured JSON extraction
- validation handoff
- fallback/debug behavior

## Preserve the central rule

Python is authoritative.

LLM creativity may only enter the world through validated boundaries.

## Scope constraints

- Do not expand the map yet.
- Do not add new gameplay features unless required to preserve existing behavior.
- Do not introduce a framework rewrite.
- Keep the standard-library-first approach.
- Preserve all existing tests.
- Add tests around newly extracted boundaries.

If a small explicit event model or command model is justified by the current code,
introduce the smallest useful version. Do not create abstractions merely because
a future game might someday need them.

## Validation

Run:

- the full unit-test suite
- terminal smoke tests
- diff/whitespace checks

Leave the working tree clean.

At the end, report:

- the resulting module boundaries
- remaining architectural pressure
- whether the code is ready for the 0.6 map expansion
