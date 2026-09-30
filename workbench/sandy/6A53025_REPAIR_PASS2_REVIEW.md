# Sandy the Skeptic — Sol adversarial re-review

review_id: `sol-38b0751-pass2-2026-09-29-sandy`

role: `Sol / adversarial review`

## input_refs

- Delivered repair: `38b0751d13dd1bf1dc3d10a67613aa75e92dcec5` (`Repair Magic Missile per Sandy REPAIR verdict on 6a53025`).
- Required comparison base: `6a530255bad75b8c4316671af8bf1f6aa96068f6`.
- Required comparison command: `git diff 6a53025 HEAD`.
- Prior receipt: `workbench/sandy/6A53025_MAGIC_MISSILE_REVIEW.md`, especially REPAIR-1 through REPAIR-4.
- Acceptance claims supplied by Foreman: wizard-only auto-hit 2d4 Magic Missile with three per-encounter charges and turn-preserving empty casts; immediate deterministic terminal output followed by non-duplicated narration without breaking recording; Python-only state authority.
- Extra pass-2 targets supplied by Foreman: narration `response` schema, fresh import order, defeat/loot helper edge cases, and the formerly surviving d6+d4 and constant-7 mutants.
- Repository rules: `AGENTS.md`.
- Current mission: `prompts/CURRENT` -> `prompts/06_DND_0_6_MAP.md`.
- Review contract: `/Users/evertj/git/foreman_interface/spells/sol.md`.

## bounded_scope

Adversarial re-review of `HEAD` against `6a53025`. No product code was implemented or repaired. Runtime probes used temporary directories and deterministic fakes. Mutants were installed only in fresh Python interpreter memory before `pytest.main(["-q"])`; no source file was mutated. The only filesystem residue created by this pass is this requested review receipt.

`6a53025` is an ancestor of `HEAD`. The required comparison also contains two intervening additive documentation commits (`c5c1a52`, `98be160`); the repair commit itself changes the four product modules, `tests/test_magic_missile.py`, and preserves the prior review receipt.

## attacks_or_checks_attempted

### Repository, diff, and baseline

- `git rev-parse HEAD 6a53025` resolved the exact refs above.
- `git merge-base --is-ancestor 6a53025 HEAD` exited 0.
- `git diff --check 6a53025 HEAD` exited 0 with no whitespace errors.
- Inspected the complete `git diff --find-renames --find-copies 6a53025 HEAD` and the complete HEAD-only commit diff.
- `python3 -m pytest -q` exited 0:

  ```text
  64 passed, 10 subtests passed in 5.76s
  ```

### REPAIR-1 through REPAIR-4 verification

- REPAIR-1 production fix is present at `dnd_combat/adventure.py:187-195`: class is checked before charge decrement or dice. A fighter with a forged current charge is rejected with unchanged enemy HP, charge, turn, and an unused roller. Removing the class check made `test_non_wizard_cannot_cast_with_forged_charge` fail.
- REPAIR-2 production fix is present at `dnd_combat/__main__.py:35-63,103-152`: attack and cast kills use the same defeat/loot helper. A spell-killed entry goblin produced one `enemy_defeated`, one `item_found`, visible ring text, and durable narration records. Removing loot emission made `test_spell_kill_emits_and_records_dropped_item` fail.
- REPAIR-3 production fix is present at `dnd_combat/terminal.py:10-25` and `dnd_combat/session_log.py:154-178`: display and recording use the same normalization. Unchanged, combined, addition-only with `DM:`, raw addition-only, empty, `None`, integer, and exception cases were exercised through `RecordingNarrator` plus `emit`. Reverting only the recorder to the old split made the addition-only test fail.
- REPAIR-4 is materially improved: the roller records requested sides and the test uses `(1,1)` and `(4,4)`. Both pass-1 survivors are now killed: d6+d4 fails on `[6,4] != [4,4]`; constant-7 fails with `7 != 2` and `7 != 8`.

### State, terminal, and command attacks

A deterministic probe exercised aliases, charges, terminal prompts, potion/status flow, terminal recording, and end states. Relevant results:

```text
aliases {'m': ('move', None), 'c': (None, 'cast'), 'cast': (None, 'cast'),
         'magic': (None, 'cast'), 'missile': (None, 'cast'),
         'magic missile': (None, 'cast'), 'use potion': ('use', 'use')}
empty None True hero 0
potion (True, 8) enemy 13 0
post-dead ValueError It is not the hero's turn. True
post-won ValueError It is not the hero's turn. True
fighter-cast False [('c', 'unrecognized or unsupported combat command'), ('attack', 'hit')]
boss won 2 ['enemy_defeated', 'victory'] []
no-loot ['enemy_defeated'] []
predead ValueError There is no active encounter in this room. False
full-main won [2, 1, 2, 1, 0] prompt-with-(3)=2 ring-notice-count=1
```

- Three casts consumed `3 -> 2 -> 1 -> 0`; a fourth cast recorded `no charges`; status remained available; a potion then worked and passed the turn. The recorded action sequence was `hit, hit, hit, no charges, status shown, potion used, attack hit`.
- Casts after forced `dead` and `won` states raised before changing charge, HP, or turn.
- A normal fighter prompt did not advertise cast; typing `c` was recorded as unsupported and did not consume the turn.
- A complete `main` wizard route cast twice at the goblin, entered the boss fight with the prompt showing three refreshed charges, cast three more times, recorded charge values `[2,1,2,1,0]`, and ended with `session_ended.result == "won"`.
- A pre-dead encounter was rejected by `start_encounter` before input or recorder output. Normal `main` cannot enter `run_combat` when no living enemy exists.

### Shared defeat/loot helper attacks

- Entry goblin spell kill: `enemy_defeated` then `item_found`; ring was present mechanically and visibly.
- Final boss spell kill: state became `won`; narration categories were exactly `enemy_defeated`, `victory`; room items remained empty.
- Enemy with explicitly cleared inventory: only `enemy_defeated`; no phantom `item_found` and no room item.
- Enemy already dead before `run_combat`: rejected with `ValueError: There is no active encounter in this room.` before helper invocation.
- A mutant that removed helper loot emission was killed, but a mutant that invoked the helper body twice survived; see REPAIR-P2-3.

### Narration, JSONL schema, and import-order attacks

The normalization/recording matrix produced:

```text
unchanged    output='PLAIN\n'             response=None    fallback=True
combined     output='PLAIN\nDM: extra\n'  response='extra' fallback=False
addition_dm  output='PLAIN\nDM: extra\n'  response='extra' fallback=False
addition_raw output='PLAIN\nextra\n'      response='extra' fallback=False
empty        output='PLAIN\n'             response=None    fallback=True
none         output='PLAIN\n'             response=None    fallback=True
integer      output='PLAIN\n'             response=None    fallback=True
exception    output='PLAIN\n'             response=None    fallback=True
```

- The pass-2 premise that the recorded `response` field changed from `""` to `null` is not borne out by the baseline source. At `6a53025:dnd_combat/session_log.py:173`, the writer already used `response=response or None`; HEAD retains that at `dnd_combat/session_log.py:174`. Only the intermediate local variable's type changed. JSONL output for no DM text remains `null`.
- The only in-repo narration-response reader is `SessionRecorder.report` at `dnd_combat/session_log.py:127-131`; it uses truthiness and correctly read synthetic legacy `""` and current `null` records as fallback. No tracked schema artifact declares a conflicting non-null string type.
- Raw `emit` with a contract-violating `None` or integer narrator prints `PLAIN` first and then raises `AttributeError`. The ordinary application path always wraps narrators in `RecordingNarrator`, which normalized both cases and exceptions to safe fallback. `Narrator.narrate` is declared to return `str`; this unchanged direct-call limitation is recorded rather than promoted to a defect.
- The following fresh-interpreter import loop exited 0 for every module, including both sides of the new dependency:

  ```sh
  for module in dnd_combat dnd_combat.session_log dnd_combat.terminal \
      dnd_combat.__main__ dnd_combat.session dnd_combat.adventure \
      dnd_combat.combat dnd_combat.commands dnd_combat.narrator \
      dnd_combat.world dnd_combat.llm_adapter dnd_combat.matching; do
    python3 -c "import $module; print('$module OK')" || exit 1
  done
  ```

- Existing hostile-narrator/deep-copy tests stayed green. Changed event packets contain derived scalar/list/dict facts rather than game objects; no narrator-to-state mutation path was found.

## commands_or_test_refs

Baseline and comparison commands:

```sh
git diff --check 6a53025 HEAD
git diff --stat 6a53025 HEAD
git diff --name-status 6a53025 HEAD
git diff --find-renames --find-copies 6a53025 HEAD
python3 -m pytest -q
```

Mutation runs used one fresh process per mutant:

```sh
for mutant in d6_d4 constant_7 four_charges no_decrement no_refresh \
  enemy_turn empty_spends_turn nonwizard_cast one_d4; do
  MUTANT="$mutant" python3 - <<'PY'
# import production symbols; install the named in-memory replacement
# raise SystemExit(pytest.main(["-q"]))
PY
done
```

The same fresh-process pattern was used for `drop_loot_emit`, `revert_recorder_split`, `false_hit`, `proxy_auth`, `zero_only_refresh`, and `duplicate_helper`.

Relevant locators:

- `dnd_combat/adventure.py:162-195` — encounter refresh and authoritative cast rule.
- `dnd_combat/combat.py:73-77` — production auto-hit 2d4.
- `dnd_combat/__main__.py:35-63,66-221` — shared helper, prompts, recording, defeat, victory/death.
- `dnd_combat/terminal.py:10-25` — shared narration normalization and immediate output.
- `dnd_combat/session_log.py:127-131,154-178` — response reader and writer.
- `tests/test_magic_missile.py:33-113,127-167` — current Magic Missile, helper, and narration regression tests.

## mutants_killed_or_survived

All results below are full-suite results after in-memory replacement; source files remained untouched.

| Mutant | Result | Disposition |
|---|---:|---|
| 2d4 -> d6+d4 | 2 failed, 64 passed, 8 subtests passed | KILLED |
| 2d4 -> constant 7 | 2 failed, 64 passed, 8 subtests passed | KILLED |
| 2d4 -> one d4 | 2 failed, 64 passed, 8 subtests passed | KILLED |
| Auto-hit result -> `hit=False` | 2 failed, 64 passed, 8 subtests passed | KILLED |
| Wizard has four charges | 4 failed, 62 passed, 8 subtests passed | KILLED |
| Successful cast does not decrement | 2 failed, 64 passed, 8 subtests passed | KILLED |
| Remove all encounter refresh | 1 failed, 63 passed, 10 subtests passed | KILLED |
| Allow cast on enemy turn | 1 failed, 63 passed, 10 subtests passed | KILLED |
| Empty cast passes turn | 1 failed, 63 passed, 10 subtests passed | KILLED |
| Remove non-wizard rejection entirely | 1 failed, 63 passed, 10 subtests passed | KILLED |
| Remove spell-kill loot emission | 1 failed, 63 passed, 10 subtests passed | KILLED |
| Revert recorder to old prefixed-only split | 1 failed, 63 passed, 10 subtests passed | KILLED |
| Authorize using `max_spell_charges > 0` instead of class | 64 passed, 10 subtests passed | **SURVIVED** |
| Refresh only when current charges are zero | 64 passed, 10 subtests passed | **SURVIVED** |
| Invoke shared defeat/loot helper twice | 64 passed, 10 subtests passed | **SURVIVED** |

## findings

### REPAIR-P2-1 — wizard-only regression test accepts mutable-max-charge authorization

Violated invariant: acceptance criterion 1 requires wizard-only authorization at Python's authoritative rule boundary, and deterministic tests must reject a plausible return of the original proxy-state defect.

Evidence: `tests/test_magic_missile.py:53-66` forges only `spell_charges = 1` on a fighter while leaving `max_spell_charges == 0`. The following broken authorization replacement passed the entire suite (`64 passed, 10 subtests passed`):

```python
if self.hero.max_spell_charges <= 0:
    raise ValueError("Only a wizard can cast magic missile.")
```

With that mutant, setting a fighter's mutable `max_spell_charges = 1` and `spell_charges = 1` permits the cast, so it does not enforce wizard identity. This is a distinct, plausible reintroduction of REPAIR-1 rather than a complaint about the correct production implementation at HEAD.

Smallest bounded repair: make the negative action-boundary test forge both current and maximum charges (or parameterize proxy states) and still require rejection with no state/roller change.

### REPAIR-P2-2 — refresh test accepts a zero-only refresh instead of per-encounter refresh

Violated invariant: acceptance criterion 1 says charges refresh at every `start_encounter`, including when a wizard carries a partially spent pool from the prior encounter.

Evidence: `tests/test_magic_missile.py:77-81` sets charges to exactly zero before starting the first encounter. A mutant that performed the otherwise-correct reset only under `if self.hero.spell_charges <= 0:` passed the entire suite (`64 passed, 10 subtests passed`). It leaves one or two carried charges unrefreshed.

The production code is correct, and the full-main runtime probe demonstrated the real `1 -> 3` refresh before the final boss. The committed regression test does not protect that real play path.

Smallest bounded repair: start an encounter from a nonzero partially spent pool (preferably the actual second encounter after one or more casts) and assert reset to exactly three.

### REPAIR-P2-3 — helper regression test accepts duplicate defeat and loot records/output

Violated invariant: deterministic presentation/session evidence should record one resolved defeat and one newly found loot event, not duplicate the same state transition. This attacks the repair's new shared helper directly.

Evidence: `tests/test_magic_missile.py:109-113` asserts only the last two narration categories and uses `assertIn` for visible loot. An in-memory mutant that called the unchanged `_emit_defeat_and_loot` body twice passed the entire suite (`64 passed, 10 subtests passed`). It emits and records `enemy_defeated, item_found, enemy_defeated, item_found` and prints both deterministic notices twice, while the current assertions still see the expected last two and substring.

Production HEAD calls the helper once and the runtime probe observed one ring notice. The defect is non-discriminating coverage of the new helper behavior, not a claim that HEAD currently duplicates it.

Smallest bounded repair: assert exact narration-category counts/order for the spell kill and exact occurrence counts for defeat/loot text; add the final-boss/no-loot case so the helper's empty-loot behavior is protected too.

## clean_results

- All four original REPAIR items are correctly implemented in production HEAD.
- The formerly surviving d6+d4 and constant-7 mutants are now killed.
- The original pass-1 mutants for charge count, successful consumption, complete refresh removal, enemy-turn casting, empty-cast turn use, and removal of wizard authorization are killed.
- Addition-only narration is both displayed and recorded accurately; unchanged/empty/invalid narration falls back safely in the ordinary wrapped application path.
- No JSONL `response` type regression occurred between the base and HEAD; both write `null` when no DM response exists, and the report reader handles `""`, `null`, and missing/falsy values.
- Fresh first-import checks found no circular-import or import-order failure.
- Final-boss, no-loot, pre-dead, dead-state, won-state, fighter-cast, status/potion, alias, and complete wizard-route probes found no production crash or state-authority failure.
- No LLM/narrator path was found that receives authoritative game state or mutates it; existing hostile narrator tests remain green.

## reproduction_limits

- No live LLM endpoint was contacted. Narration probes used deterministic fakes; transport/fallback behavior remains covered by the existing suite.
- Mutants were symbol-level in-memory replacements. They establish whether the committed suite rejects the behavior without altering the worktree.
- Direct raw `emit` does not normalize a narrator that violates its declared `str` return contract. The actual `main` path always installs `RecordingNarrator`, and both `None` and integer results plus ordinary exceptions were contained there.
- `_emit_defeat_and_loot` is internal and assumes a caller-proven fresh defeat. The production `run_combat` call sites satisfy that condition; the duplicate-helper finding concerns missing regression discrimination, not an observed production duplicate.

## next_action

Return to Foreman for a bounded test-only repair of the three surviving mutants. Production logic should not be rewritten based on this pass. After the tests discriminate forged maximum-charge authorization, partial-pool encounter refresh, and duplicate helper output/records, run the deterministic suite and a fresh Sandy re-review.

terminal_state: `COMPLETE`

VERDICT: REPAIR
