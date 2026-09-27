# Penny's Pile — D&D Builder Track

Status: ACTIVE EXPERIMENTAL BACKLOG

This is the project-owned pile of meaningful D&D build directions that Penny may plan from.

It is **not** Brenda's task list.

Penny reads current project truth, selects one READY item, and converts only the next bounded slice into a Brenda work unit. Brenda never reads this pile and never chooses what comes next.

## Standing project truth

Before Penny plans anything, read at minimum:

- `AGENTS.md`
- `README.md`
- `docs/PLAY_DESIGN.md`
- `docs/REMOTE_LLM_ARCHITECTURE.md`
- `prompts/CURRENT`
- relevant implementation files and tests for the chosen pile item

Current architectural invariant:

> **Python is authoritative. The LLM is creative, not sovereign.**

Current play-design north star:

> **Build the smallest world that can remember the player. Then make that memory matter.**

## How Penny uses this pile

For one READY item:

1. Reconcile the item against current repository truth. Do not trust this file if code/tests say otherwise.
2. Decide the smallest next build slice that materially advances the item.
3. Write exactly one Brenda work unit.
4. Give Brenda explicit read paths, write paths, proof commands, and a finite model-step budget.
5. Do not give Brenda project-planning work.
6. Do not give Brenda multiple separable responsibilities in one unit.
7. After Brenda stops, Sandy independently compares Penny's unit with Brenda's result.
8. If Sandy returns FAIL, Annabelle reviews the failed unit/run and decides what local Brenda/workbench correction is warranted.
9. A scope violation is never repaired in-place. Preserve evidence, classify the failure, then nuke the worktree and retry from a fresh baseline after correction.

## Pile

### P-001 — Natural-language intent pilot

**Status:** READY

Make one narrow unusual player intent feel natural without surrendering authority to the narrator.

Candidate player intents from the existing design:

- "I show the ring to Mira."
- "I listen before going north."
- "I wedge the bent spoon under the door."

The first implementation should cover **one** deliberately chosen intent, not a general semantic parser.

Success at the pile level means:

- free text can be interpreted into a bounded candidate action;
- Python validates whether that action exists and whether it may affect state;
- deterministic behavior remains playable when the LLM is absent;
- malformed or imaginative model output cannot invent new mechanics;
- the experience is visibly more natural to play.

Penny chooses the first tiny slice after inspecting current commands, matching, session, world, and tests.

---

### P-002 — NPC memory pilot

**Status:** READY AFTER P-001 OR HUMAN CHOICE

Give one important NPC a very small structured memory of player behavior and make one later interaction depend on it.

Do not build a general agent-memory framework.

Pile-level target:

- memory is explicit structured Python-owned state;
- one earlier player action creates or changes one memory;
- one later NPC interaction deterministically notices it;
- the model may express the reaction but may not invent the remembered fact;
- replay from a clean baseline is deterministic where expected.

---

### P-003 — Hidden world-state pilot

**Status:** READY AFTER EARLIER PILOT OR HUMAN CHOICE

Create one hidden fact that the narrator does not receive until it becomes relevant.

Examples:

- an NPC secret;
- an unrevealed room fact;
- a future consequence flag.

Pile-level target:

- Python owns the hidden truth;
- narration cannot retroactively rewrite it;
- reveal conditions are deterministic;
- tests prove the fact remains hidden before the reveal and stable after it.

---

### P-004 — Event oracle pilot

**Status:** SHELF

Add one deterministic or seeded event source that changes world state before narration describes it.

Do not build a simulation engine.

The event must create consequence rather than merely additional prose.

---

### P-005 — Richer progression pilot

**Status:** SHELF

Track one non-loot form of player progression such as reputation, relationship, discovered fact, or recurring consequence.

The first version should be one field or one tiny structured record with a visible later effect.

---

### P-006 — D&D playability cleanup from human evidence

**Status:** CONTINUOUS / EVIDENCE-DRIVEN

Use actual human playtest evidence to create narrowly scoped build candidates.

Candidate signals:

- unsupported player attempt;
- world felt fake;
- narration was slow;
- prior action should have mattered but did not;
- player expected an object/NPC/room to remember something;
- player wanted to try something the command surface could not express.

This item never authorizes broad polish. Penny must tie each unit to concrete playtest evidence.

## Explicit non-goals

The pile does not currently authorize:

- GUI work;
- voice/TTS work;
- multiplayer;
- a general agent framework;
- autonomous NPC swarms;
- a database merely for future scale;
- moving mechanical authority into an LLM;
- a giant natural-language action framework;
- broad refactors not required by the selected pile item.

## Experimental rule

For Brenda calibration, prefer a known pile item and stable baseline.

When Brenda architecture changes after a Sandy FAIL / Annabelle correction:

1. preserve the failed run and receipts;
2. remove the failed Brenda worktree;
3. return to the same project baseline;
4. rerun the same Penny unit when practical;
5. compare outcomes.

Improvement must survive a fresh run. Do not repair history until it looks successful.
