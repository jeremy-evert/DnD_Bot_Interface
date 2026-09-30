<!-- Provenance: Genny deleted the original REVIEW_SANDY.md by mistake (removed its worktree before copying). This text was recovered from the Codex session log rollout-2026-09-29T22-59-46-01a0f077-eb0d-75b3-856b-fb865859da94.jsonl (Sandy's apply_patch content). Reviewer: gpt-5.6-sol, high. -->
# Sandy the Skeptic — Sol adversarial review

review_id: `sol-6a53025-2026-09-29-sandy`

role: `Sol / adversarial review`

## input_refs

- Delivered result: commit `6a530255bad75b8c4316671af8bf1f6aa96068f6` (`Wizard gets Magic Missile; show engine text before narration arrives`).
- Comparison base: first parent `94af79a9676cc2fef59bcc63fa9155c3c83f40af`.
- Comparison command: `git diff 6a53025~1 6a53025`.
- Worker output inspected: the seven changed paths in that diff and commit message. No separate worker receipt or accepted implementation plan was supplied.
- Acceptance criteria supplied by Foreman:
  1. Magic Missile is wizard-only, auto-hit 2d4, has three per-encounter charges, does not spend the turn when empty, and refreshes at `start_encounter`.
  2. `terminal.emit` prints deterministic text immediately and narration afterward without duplicate deterministic text or broken recording/tests.
  3. Python remains authoritative and narration cannot mutate state.
- Repository rules: `AGENTS.md`.
- Current mission: `prompts/CURRENT` -> `prompts/06_DND_0_6_MAP.md`, including deterministic testing and session-recording requirements.
- Review contract: `/Users/evertj/git/foreman_interface/spells/sol.md`.

## bounded_scope

Read-only adversarial review of commit `6a53025` against its first parent. Product code was not implemented or repaired. Probes used deterministic in-process fakes, temporary session logs under the cwd, and in-memory monkeypatch mutants; temporary files were cleaned up.

## attacks_or_checks_attempted

### Baseline and comparison checks

- `git rev-parse HEAD 6a53025 6a53025~1` confirmed that the detached worktree is exactly the subject commit and resolved the stated parent.
- `git diff --stat 6a53025~1 6a53025`, `git diff --name-status ...`, and the full diff were inspected.
- `git diff --check 6a53025~1 6a53025` exited 0 with no whitespace errors.
- `python3 -m pytest -q` exited 0: `61 passed, 5 subtests passed in 5.58s`.

### Runtime and state attacks

- Exercised exactly three casts, a fourth empty cast, enemy turn transitions, and potion use after an empty cast. Production requested die sizes `[4, 4]` for each successful cast; charges went `3 -> 2 -> 1 -> 0`; the empty cast changed neither HP nor turn; the subsequent potion worked and spent the turn.
- Exercised casts after manually setting game state to `dead` and `won`. Both raised `ValueError` before spending a charge.
- Exercised `run_combat` with no living enemy. `start_encounter` raised `ValueError: There is no active encounter in this room.`; normal `main` does not enter `run_combat` unless `game.in_combat` is true.
- Exercised a fighter typing `c` in terminal combat. The command was recorded as unsupported, the turn remained available, and the fighter then attacked normally. The fighter prompt did not advertise casting.
- Exercised a wizard killing both the entry goblin and final boss with Magic Missile through `main`, with a real `SessionRecorder`. Both casts were recorded; charges refreshed for the later encounter; the final cast produced `won`, victory narration, and `session_ended` with result `won`.
- Exercised entry-goblin spell death against the attack-death path. Mechanical loot dropped in both, but only the attack path emitted/recorded `item_found`; see REPAIR-2.
- Checked command aliases in both contextual resolvers. Results were clean: exploration `m -> move`, combat `m -> None`, exploration `c -> None`, combat `c/cast/magic/missile/magic missile -> cast`, and `use potion -> use` in both contexts. No exploration/combat collision was found.
- Read the prompt construction in `dnd_combat/__main__.py:63-69` and captured prompt arguments. Wizard: `Your turn. [A]ttack, [C]ast magic missile (3), [U]se potion, [S]tatus: `; fighter: `Your turn. [A]ttack, [U]se potion, [S]tatus: `.

### Narration, authority, and recording attacks

- A slow narrator printed `[model call]` while being invoked. Existing test `tests/test_magic_missile.py:73-78` and the baseline run established the order `plain text`, model call, narration.
- Narrator returned the unchanged plain text: printed once.
- Narrator returned an addition that did not begin with `plain_text`: output was `PLAIN\
- Narrator returned an empty string: output was only `PLAIN\
- A raw narrator returned `None` or `42`: `emit` first printed `PLAIN\
- A valid addition-only LLM-style narrator was wrapped in `RecordingNarrator`. The addition was displayed, but the session event recorded `response=None` and `fallback=True`; see REPAIR-3.
- Existing hostile-narrator/deep-copy tests remained green. The changed call sites pass derived scalar/list/dict facts rather than game objects, and no narrator-driven state mutation was found.

## commands_or_test_refs

Baseline:

```console
$ python3 -m pytest -q
.............................................................       [100%]
61 passed, 5 subtests passed in 5.58s
```

Wizard-only action-boundary reproduction:

```console
$ python3 - <<'PY'
from dnd_combat.adventure import Adventure, make_character

class R:
    def __init__(self, *values): self.values = iter(values)
    def __call__(self, sides): return next(self.values)

game = Adventure(make_character("fighter", "Arin"))
game.start_encounter(R(20, 1))
game.hero.spell_charges = 1
result = game.player_cast_magic_missile(R(2, 3))
print(result.damage, game.hero.spell_charges, game.combat_turn)
PY
5 0 enemy
```

Addition-only recording reproduction:

```console
$ python3 - <<'PY'
import io, json, tempfile
from contextlib import redirect_stdout
from pathlib import Path
from dnd_combat.narrator import Narrator
from dnd_combat.session_log import RecordingNarrator, SessionRecorder
from dnd_combat.terminal import emit

class AdditionOnlyLLM(Narrator):
    adapter = object()
    model = "probe"
    def narrate(self, event, facts, plain_text): return "DM: addition only"

with tempfile.TemporaryDirectory(dir=".") as directory:
    recorder = SessionRecorder(Path(directory) / "addition.jsonl")
    output = io.StringIO()
    with redirect_stdout(output):
        emit(RecordingNarrator(AdditionOnlyLLM(), recorder), "event", {}, "PLAIN")
    event = json.loads(recorder.path.read_text())
    print(repr(output.getvalue()), event["response"], event["fallback"])
PY
'PLAIN\
```

Relevant source/test locators:

- `dnd_combat/adventure.py:181-194` — cast action checks encounter/turn and charges, but not class/entitlement.
- `dnd_combat/world.py:43-58` — factory defaults hide the missing action authorization by assigning zero charges to non-wizards.
- `dnd_combat/combat.py:73-77` — production 2d4 implementation is correct in this commit.
- `dnd_combat/__main__.py:72-149` — attack death handles new loot; cast death does not.
- `dnd_combat/terminal.py:10-19` — immediate print and narration splitting.
- `dnd_combat/session_log.py:153-177` — recorder recognizes a response only after the exact `\
- `tests/test_magic_missile.py:11-16,29-39` — roller ignores requested side count and only one sum is asserted.

## mutants_killed_or_survived

Each mutant was installed only in memory before `pytest.main(['-q'])`; no source file was edited.

| Mutant | Full-suite result | Disposition |
|---|---:|---|
| Replace 2d4 with one d4 | 1 failed, 60 passed, 5 subtests passed | KILLED by damage assertion |
| Replace 2d4 with d6+d4, keeping the supplied values 3 and 4 | 61 passed, 5 subtests passed | **SURVIVED** |
| Replace both rolls with hard-coded damage 7 | 61 passed, 5 subtests passed | **SURVIVED** |
| Give wizard four initial/max charges | 3 failed, 58 passed, 5 subtests passed | KILLED |
| Do not decrement a charge on a successful cast | 1 failed, 60 passed, 5 subtests passed | KILLED |
| Drop the `start_encounter` refresh | 1 failed, 60 passed, 5 subtests passed | KILLED |
| Allow casting on the enemy turn | 1 failed, 60 passed, 5 subtests passed | KILLED |
| Make an empty cast pass the turn | 1 failed, 60 passed, 5 subtests passed | KILLED |
| Allow a non-wizard with a positive current charge to cast | Production already has this behavior; baseline suite passes | **SURVIVED / PRESENT** |

## findings

### REPAIR-1 — the authoritative cast action does not enforce “wizard only”

Violated criterion: acceptance criterion 1 and the Python-authority invariant.

Evidence: `dnd_combat/adventure.py:187-193` validates only active combat, hero turn, and a positive mutable `spell_charges` value. It never checks `character_class` or another immutable spell entitlement. The exact production-API reproduction above starts a fighter encounter, assigns one current charge, and successfully deals 5 damage, consumes the charge, and passes the turn. Expected: the non-wizard action is rejected without damage, charge use, or turn use.

This is not inferred from a worker claim or a synthetic replacement: it executes the delivered `Adventure.player_cast_magic_missile` method. Normal construction masks the defect by supplying zero charges, and the terminal adds a second `max_spell_charges` guard, but Python's authoritative rule boundary itself does not preserve the claimed invariant.

Smallest bounded repair: enforce spell entitlement at the rule action and add a negative test that grants/forges a charge on a fighter but still cannot cast. Foreman should choose the representation of entitlement.

### REPAIR-2 — a spell kill drops loot but skips its deterministic notification and narration/session record

Violated invariant: the current mission requires important deterministic outcomes/state changes to remain reconstructable, and the new action should preserve existing defeat/loot presentation and recording behavior.

Evidence: the attack branch snapshots `items_before` and emits `item_found` at `dnd_combat/__main__.py:73-119`. The cast branch at `dnd_combat/__main__.py:121-149` emits only `enemy_defeated`. A deterministic `run_combat` probe with the entry goblin at 1 HP produced:

```text
wizard_cast_entry_kill ... narrations=['enemy_defeated']
output='... Cy hurls a magic missile ...\
```

The otherwise equivalent fighter attack produced `narrations=['enemy_defeated', 'item_found']` and `You notice goblin's brass ring among the fallen Goblin.` Mechanical state is not lost: `_finish_or_pass_turn` drops the ring and `main`'s post-combat `look()` later reveals it. The defect is the omitted immediate notification and durable narration event for the new kill route.

Smallest bounded repair: share or mirror the already-existing post-defeat loot notification path for successful spell kills, with a terminal/recorder regression test.

### REPAIR-3 — valid addition-only narration is displayed but falsely recorded as fallback

Violated criterion: acceptance criterion 2's requirement that the new `emit` behavior coexist with `RecordingNarrator`/`session_log`.

Evidence: `terminal.emit` explicitly supports a string that does not start with `plain_text` by printing it as the addition. However, `dnd_combat/session_log.py:165-174` records a response only if the rendered string contains the exact `\

This is not the non-string robustness probe: the narrator returns a valid ordinary `str` conforming to `Narrator.narrate`'s declared type. It exercises the non-prefixed-output branch that `emit` itself now supports.

Smallest bounded repair: define one normalized rendering/recording contract for unchanged plain text, prefixed combined text, and addition-only text, then test all three through `RecordingNarrator` plus `emit`.

### REPAIR-4 — the claimed 2d4 regression test accepts materially wrong dice implementations

Violated invariant: deterministic tests must discriminate the named mechanic; Sol's contract requires attempting a plausible broken implementation.

Evidence: `tests/test_magic_missile.py:11-16` ignores the `sides` argument, while the only damage case at lines 29-39 supplies 3 and 4 and asserts only their sum, 7. The full suite stayed completely green when 2d4 was replaced with d6+d4, and also when all rolling was removed in favor of hard-coded damage 7. Production source is correct and a side-recording runtime probe observed `[4, 4]`, but the committed test does not protect that behavior.

Smallest bounded repair: make the deterministic roller assert/record requested die sizes and use enough result vectors to reject a constant implementation.

## clean_results

- Production currently calls the roller twice with d4, always returns `hit=True`, clamps target HP at zero, and decrements exactly one charge.
- Three charges, successful-cast consumption, empty-cast turn preservation, encounter refresh, and enemy-turn rejection all killed their corresponding mutants except the separately established class-authorization gap.
- Terminal fighter input cannot reach casting under normally constructed state.
- The final-boss spell path reached victory without a crash and wrote a complete `session_ended` event.
- Empty and ordinary non-prefixed narrator strings rendered correctly; standard prefixed narration was not duplicated.
- `RecordingNarrator` safely normalized non-string/exceptional narrator failures in the normal `main` path.
- Existing hostile narrator tests and the full deterministic suite passed; no narrator mutation of game state was found.
- Context-specific command aliases did not collide.

## reproduction_limits

- No live remote/local model endpoint was contacted; narration probes were deterministic fakes. The production adapter's timeout/invalid-content fallback was inspected and its existing deterministic tests passed.
- Mutants were symbol-level in-process replacements, not textual edits. They test whether the collected suite rejects the changed behavior while preserving the worktree.
- REPAIR-1 requires manually injecting a positive current charge into a fighter. No normal terminal command currently grants that charge; the finding is that the authoritative action does not enforce its own advertised class invariant.
- Direct raw `emit` calls with non-string returns crash, but the ordinary `main` path wraps narrators and safely normalizes them. This boundary was recorded rather than promoted into a separate finding.
- A direct `run_combat` call with no living enemy rejects at `start_encounter`; normal `main` guards this path.

## next_action

Return to Foreman for bounded repair of the rule authorization, spell-kill loot notification/recording parity, addition-only narration recording, and discriminating 2d4 tests. After repair, run the full deterministic suite and a fresh Sandy pass. No Astra escalation is warranted from these bounded defects.

terminal_state: `COMPLETE`

VERDICT: REPAIR
