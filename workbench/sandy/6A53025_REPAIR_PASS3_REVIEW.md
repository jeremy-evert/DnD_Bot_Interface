# Sandy the Skeptic — Sol adversarial re-review, pass 3

review_id: `sol-1bd2124-pass3-2026-09-29-sandy`

role: `Sol / adversarial review`

## input_refs

- Delivered repair under review: `1bd2124ffce8e150bdf6fe0c1ea45713e62ca533` (`Tighten Magic Missile tests per Sandy pass 2 (P2-1..3)`).
- Product repair: `38b0751d13dd1bf1dc3d10a67613aa75e92dcec5` (`Repair Magic Missile per Sandy REPAIR verdict on 6a53025`).
- Required comparison base: `6a530255bad75b8c4316671af8bf1f6aa96068f6`.
- Required comparison command: `git diff 6a53025 HEAD`.
- Prior receipts: `workbench/sandy/6A53025_MAGIC_MISSILE_REVIEW.md` and `workbench/sandy/6A53025_REPAIR_PASS2_REVIEW.md`, including REPAIR-1..4 and REPAIR-P2-1..3.
- Acceptance claims supplied by Foreman: wizard-only auto-hit 2d4 Magic Missile with three per-encounter charges and a turn-preserving empty cast; immediate deterministic terminal text followed by non-duplicated narration without recording regression; Python-only authority over state.
- Pass-3 instruction supplied by Foreman: product code is unchanged since pass 2; re-run every earlier mutant, especially the three pass-2 survivors, and try at least three new plausible mutants.
- Repository rules: `AGENTS.md`.
- Current mission: `prompts/CURRENT` -> `prompts/06_DND_0_6_MAP.md`.
- Review contract: `/Users/evertj/git/foreman_interface/spells/sol.md`.

## bounded_scope

Adversarial re-review of `HEAD` against `6a53025`. I did not implement or repair product code. All mutants were installed only in fresh Python interpreter memory before `pytest.main(["-q"])`; no source file was mutated. Runtime artifacts used temporary directories. The only lasting filesystem residue from this pass is this requested receipt.

`git diff --exit-code 38b0751 HEAD -- dnd_combat` exited 0, confirming the pass-3 commit is test-only with respect to product code. The full required comparison also contains the product repair, the prior receipts, and two additive documentation commits inherited between the requested base and repair.

## attacks_or_checks_attempted

### Repository, diff, and baseline

- `git rev-parse HEAD 6a53025 38b0751` resolved the three exact hashes above.
- `git merge-base --is-ancestor 6a53025 HEAD` exited 0.
- `git diff --check 6a53025 HEAD` exited 0.
- Inspected the complete HEAD-only test diff and the product/test portion of `git diff --find-renames --find-copies 6a53025 HEAD`.
- `python3 -m pytest -q` exited 0:

  ```text
  65 passed, 12 subtests passed in 5.87s
  ```

### Pass-2 findings REPAIR-P2-1..3

- REPAIR-P2-1 is discriminated at `tests/test_magic_missile.py:53-70`: both `spell_charges` and `max_spell_charges` are forged on a fighter in two proxy-state cases. The prior `max_spell_charges > 0` authorization mutant now fails both subtests.
- REPAIR-P2-2 is discriminated at `tests/test_magic_missile.py:81-95`: a real first encounter spends the pool from three to two, then the second encounter must restore three. The prior zero-only refresh mutant now fails.
- REPAIR-P2-3 is discriminated at `tests/test_magic_missile.py:107-160`: narration categories and rendered notices have exact order/counts, and a final-boss no-loot case is covered. The prior duplicate-helper mutant now fails both spell-kill tests.

### REPAIR-1..4 and earlier-mutant replay

- REPAIR-1 remains correctly implemented at `dnd_combat/adventure.py:187-195`; non-wizard rejection occurs before charge use or rolling. Both the total removal of authorization and the mutable-max-charge proxy mutant are killed.
- REPAIR-2 remains correctly implemented through `_emit_defeat_and_loot` at `dnd_combat/__main__.py:35-63,125-152`; removing spell-kill loot emission is killed.
- REPAIR-3 remains correctly implemented at `dnd_combat/terminal.py:10-25` and `dnd_combat/session_log.py:154-178`; reverting the recorder to prefixed-only response extraction is killed.
- REPAIR-4 remains correctly implemented at `dnd_combat/combat.py:73-77` and discriminated by `tests/test_magic_missile.py:37-51`. Both formerly surviving d6+d4 and constant-7 mutants are killed, as are one-d4 and false-hit variants.
- Four initial charges, no successful-cast decrement, no refresh, enemy-turn casting, an empty cast spending the turn, and decrement-by-two are all killed.

### New mutation attacks

Six new plausible mutants were run against the full suite:

1. Remove Magic Missile's `max(0, ...)` HP clamp.
2. Remove `flush=True` from the first deterministic print in `emit` while preserving print order.
3. Have the shared helper announce every current room item instead of only items absent from `items_before`.
4. Emit new loot before `enemy_defeated`.
5. Treat combined `plain_text + DM` output as an undivided addition, duplicating plain text.
6. Spend two charges per successful cast.

The first three survived; the last three were killed. Direct counterexamples established that each survivor is materially broken rather than an equivalent implementation:

```text
no-HP-clamp: damage 8 from HP 1 -> HP -7; expected floor 0
no-flush: buffered stream visible to narrator was ''; production exposes 'NOW\n' after one flush
helper-all-items: killing the no-loot Bone Sentinel falsely records clay cup as item_found
```

### State, prompt, helper, and recorder attacks

- A normal fighter typed `c`, received an unsupported-command record, retained the hero turn, then attacked successfully. Neither fighter prompt advertised casting.
- A final-boss spell kill ended in `won`, clamped boss HP to 0, left two charges, showed the three-charge prompt, recorded exactly `enemy_defeated, victory`, and produced no loot.
- `run_combat` on an already-dead enemy raised `ValueError: There is no active encounter in this room.` before setting `encounter_started`.
- Casts after forced `dead` and `won` states raised before changing charge, HP, or turn.
- A fourth/empty cast preserved HP and the hero turn; a healing potion then healed 8 and passed the turn normally. Status remains a non-turn action in the unchanged terminal branch.
- Contextual alias results remained non-colliding: exploration `m -> move`, combat `m -> None`; exploration `c -> None`, combat `c/cast/magic/missile/magic missile -> cast`; `use potion -> use` in both contexts.
- The production helper was exercised with a pre-existing takeable room item plus dropped loot: it announced only the newly dropped brass ring. It was also exercised in the real cistern, where the no-loot Bone Sentinel left the pre-existing clay cup unannounced.
- Overkill with production Magic Missile dealt 8 to an enemy at 1 HP and left HP at exactly 0.

### Narration, response schema, imports, and authority

The raw and ordinary wrapped narration matrices produced:

```text
raw addition "DM: extra" -> 'PLAIN\nDM: extra\n'
raw addition "extra"     -> 'PLAIN\nextra\n'
raw empty string          -> 'PLAIN\n'
raw None / integer        -> prints 'PLAIN\n', then AttributeError

RecordingNarrator unchanged -> response=None, fallback=True
RecordingNarrator combined  -> response='extra', fallback=False
RecordingNarrator DM-only   -> response='extra', fallback=False
RecordingNarrator raw-only  -> response='extra', fallback=False
RecordingNarrator empty     -> response=None, fallback=True
RecordingNarrator None/int  -> response=None, fallback=True
```

- A stream spy observed `plain_text` plus one flush before the narrator was invoked in production.
- The pass-2 premise that the JSONL `response` field changed from `""` to `null` remains false. At `6a53025:dnd_combat/session_log.py:173`, the writer already used `response=response or None`; HEAD does the same at line 174. Only the intermediate extraction changed.
- `rg` found the narration-response reader at `SessionRecorder.report` (`dnd_combat/session_log.py:127-131`) and test consumers. A synthetic report containing legacy `""`, current `null`, and text values rendered both falsy values as deterministic fallback and the text value as DM output. No conflicting tracked schema declaration was found.
- Fresh-interpreter imports of `dnd_combat`, `session_log`, `terminal`, `__main__`, `session`, `adventure`, `combat`, `commands`, `narrator`, `world`, `llm_adapter`, and `matching` all exited 0 regardless of importing each named module first. No circular-import or import-order failure was found.
- `tests/test_terminal_smoke.py::TerminalSmokeTests::test_mutate_then_raise_preserves_original_narration_facts` and the full hostile-narrator suite stayed green. Narrators receive deep-copied derived fact packets, not `Adventure`, `Creature`, `Room`, or another authoritative state object. No narrator-to-state mutation path was found.

## commands_or_test_refs

Baseline and comparison:

```sh
git rev-parse HEAD 6a53025 38b0751
git merge-base --is-ancestor 6a53025 HEAD
git diff --check 6a53025 HEAD
git diff --find-renames --find-copies 6a53025 HEAD
git diff --exit-code 38b0751 HEAD -- dnd_combat
python3 -m pytest -q
```

Fresh import-order check:

```sh
for module in dnd_combat dnd_combat.session_log dnd_combat.terminal \
  dnd_combat.__main__ dnd_combat.session dnd_combat.adventure \
  dnd_combat.combat dnd_combat.commands dnd_combat.narrator \
  dnd_combat.world dnd_combat.llm_adapter dnd_combat.matching; do
  python3 -c "import $module; print('$module OK')" || exit 1
done
```

Mutation runs used a fresh process per named in-memory replacement:

```sh
for mutant in d6_d4 constant_7 one_d4 false_hit four_charges no_decrement \
  no_refresh enemy_turn empty_spends_turn nonwizard_cast drop_loot_emit \
  revert_recorder_split proxy_auth zero_only_refresh duplicate_helper; do
  MUTANT="$mutant" python3 - <<'PY'
# import production symbols; install only the selected in-memory replacement
# run pytest.main(["-q"]); print exit code and summary
PY
done

for mutant in no_hp_clamp no_flush helper_all_items loot_before_defeat \
  duplicate_combined decrement_two; do
  MUTANT="$mutant" python3 - <<'PY'
# same isolated full-suite mutation pattern
PY
done
```

Targeted authority/recording regressions:

```sh
python3 -m pytest -q \
  tests/test_terminal_smoke.py::TerminalSmokeTests::test_mutate_then_raise_preserves_original_narration_facts \
  tests/test_magic_missile.py::InstantTextTests::test_recording_and_emit_share_narration_contract \
  tests/test_magic_missile.py::MagicMissileTests::test_final_boss_spell_kill_emits_defeat_without_loot
```

Result: `3 passed, 3 subtests passed in 0.41s`.

Relevant locators:

- `dnd_combat/adventure.py:162-195` — refresh and authoritative cast checks.
- `dnd_combat/combat.py:73-77` — auto-hit 2d4 and HP clamp.
- `dnd_combat/__main__.py:35-63,66-221` — helper, prompt, recorder path, and end states.
- `dnd_combat/terminal.py:10-25` — normalization, immediate flush, and addition display.
- `dnd_combat/session_log.py:127-131,154-178` — response reader and writer.
- `tests/test_magic_missile.py:37-160,174-214` — repaired Magic Missile/helper/emit tests.

## mutants_killed_or_survived

All results are full-suite results after fresh-process in-memory replacement; source files remained untouched.

| Mutant | Full-suite result | Disposition |
|---|---:|---|
| 2d4 -> d6+d4 | 2 failed, 65 passed, 10 subtests passed | KILLED |
| 2d4 -> constant 7 | 2 failed, 65 passed, 10 subtests passed | KILLED |
| 2d4 -> one d4 | 2 failed, 65 passed, 10 subtests passed | KILLED |
| Auto-hit result -> `hit=False` | 2 failed, 65 passed, 10 subtests passed | KILLED |
| Wizard starts with four charges | 4 failed, 63 passed, 10 subtests passed | KILLED |
| Successful cast does not decrement | 3 failed, 64 passed, 10 subtests passed | KILLED |
| Remove all encounter refresh | 1 failed, 64 passed, 12 subtests passed | KILLED |
| Allow cast on enemy turn | 1 failed, 64 passed, 12 subtests passed | KILLED |
| Empty cast passes turn | 1 failed, 64 passed, 12 subtests passed | KILLED |
| Remove non-wizard rejection | 2 failed, 65 passed, 10 subtests passed | KILLED |
| Remove spell-kill loot emission | 1 failed, 64 passed, 12 subtests passed | KILLED |
| Revert recorder to prefixed-only split | 1 failed, 64 passed, 12 subtests passed | KILLED |
| Authorize using mutable maximum charges | 2 failed, 65 passed, 10 subtests passed | KILLED |
| Refresh only when current charges are zero | 1 failed, 64 passed, 12 subtests passed | KILLED |
| Invoke shared defeat/loot helper twice | 2 failed, 63 passed, 12 subtests passed | KILLED |
| **NEW:** spend two charges | 3 failed, 64 passed, 10 subtests passed | KILLED |
| **NEW:** emit loot before defeat | 1 failed, 64 passed, 12 subtests passed | KILLED |
| **NEW:** duplicate combined plain+narration text | 3 failed, 62 passed, 11 subtests passed | KILLED |
| **NEW:** remove Magic Missile HP clamp | 65 passed, 12 subtests passed | **SURVIVED** |
| **NEW:** omit the immediate print's flush | 65 passed, 12 subtests passed | **SURVIVED** |
| **NEW:** helper announces all room items | 65 passed, 12 subtests passed | **SURVIVED** |

## findings

### REPAIR-P3-1 — Magic Missile tests accept negative HP on overkill

Violated invariant: Python owns HP and death, and the new Magic Missile mechanic must preserve the engine's zero-floor HP semantics. Production correctly applies `max(0, defender.hp - damage)` at `dnd_combat/combat.py:76`; the regression suite must discriminate its removal.

Evidence: an in-memory mutant replacing that assignment with `defender.hp -= damage` passed the entire suite (`65 passed, 12 subtests passed`). A direct counterexample at target HP 1 with rolls `(4, 4)` produced damage 8 and HP `-7`, whereas production produced HP `0`. Existing boundary vectors at `tests/test_magic_missile.py:37-51` do not overkill; spell-kill tests at lines 107-160 assert death/events but not HP.

Smallest bounded repair: add an overkill assertion that Magic Missile leaves enemy HP exactly zero, preferably in an existing spell-kill test. Product code should not change for this finding.

### REPAIR-P3-2 — immediate-output test accepts removal of the required flush

Violated criterion: acceptance criterion 2 requires deterministic text to be visible immediately before narrator latency. Source order alone is insufficient on a buffered stream; `flush=True` at `dnd_combat/terminal.py:21` is the mechanism establishing the claim.

Evidence: an `emit` mutant that kept `print(plain_text)` before `narrator.narrate(...)` but omitted `flush=True` passed the entire suite (`65 passed, 12 subtests passed`). With a deterministic buffered stream that exposes writes only on `flush`, production let the narrator observe `NOW\n` and one flush; the mutant invoked the narrator while visible output was still empty. `tests/test_magic_missile.py:174-179` uses `StringIO`, which exposes writes without a flush and therefore cannot reject this regression.

Smallest bounded repair: make the timing test use a flush-aware buffered spy or mock the first `print` and require `flush=True` before the narrator call. Product code should not change for this finding.

### REPAIR-P3-3 — helper tests accept false loot events for pre-existing room items

Violated invariant: `_emit_defeat_and_loot` must report newly dropped loot, not attribute unrelated persistent room objects to the defeated enemy. Truthful deterministic session evidence is part of the current mission.

Evidence: an in-memory helper mutant replacing the `items_before` difference at `dnd_combat/__main__.py:51` with iteration over all `game.room.items` passed the entire suite (`65 passed, 12 subtests passed`). The real cistern already supplies the counterexample: it contains a takeable `clay cup`, and the Bone Sentinel carries no loot. Production records only `enemy_defeated`; the surviving mutant additionally records `item_found: clay cup` and describes it as among the fallen sentinel. Current helper tests cover new loot in an otherwise empty room and a final boss in an empty room, but not a no-loot enemy beside a pre-existing takeable item.

Smallest bounded repair: add a spell- or attack-kill test in the cistern (or inject a pre-existing takeable object) and assert exact narration categories contain no `item_found` and no false `You notice` output. Product code should not change for this finding.

## clean_results

- Every original REPAIR-1..4 behavior is correctly implemented in production HEAD.
- Every earlier mutant from passes 1 and 2 is now killed, including d6+d4, constant-7, mutable-maximum authorization, zero-only refresh, and duplicate helper invocation.
- The pass-2 `response`-schema concern is disproved: both base and HEAD serialize absent narration as JSON `null`, and the report reader tolerates legacy empty string, current null, and missing/falsy values.
- Fresh import-first checks found no circular import or import-order regression from `session_log -> terminal`.
- Final boss, no loot, pre-dead enemy, dead/won state, fighter input, empty-cast potion flow, alias context, and recorder paths did not crash or violate authoritative state.
- Plain text is flushed before production narrator invocation; combined narration is not duplicated; addition-only narration is displayed and recorded; empty narration falls back.
- Production HP clamping and helper item-snapshot logic are correct. The three findings are non-discriminating test coverage, not present product defects.
- No LLM/narrator state-mutation path was found; hostile narrators receive copied facts and ordinary narrator failure cannot block deterministic play.

## reproduction_limits

- No live LLM endpoint was contacted. Narration and failure probes used deterministic fakes; transport behavior remains covered by the deterministic suite.
- Mutants were symbol-level in-memory replacements, not textual edits. They establish whether the committed suite rejects each behavior while preserving the worktree.
- Raw `emit` with a contract-violating `None` or integer narrator prints deterministic text first and then raises `AttributeError`. The application path wraps narrators in `RecordingNarrator`, which converts these values and ordinary exceptions to safe fallback, and `Narrator.narrate` is declared to return `str`; this unchanged direct-call limitation is not promoted to a finding.
- The no-flush counterexample uses a deliberately buffered stream. Interactive TTYs are often line-buffered, but the acceptance claim is explicit and production itself uses `flush=True`; the mutant demonstrates that the present test proves call order but not immediate visibility.

## next_action

Return to Foreman for a bounded test-only repair of REPAIR-P3-1..3: pin zero-floor overkill HP, flush-before-narrator visibility, and exclusion of pre-existing room items from loot events. Do not rewrite product logic based on this pass. Then run the deterministic suite and a fresh Sandy re-review.

terminal_state: `COMPLETE`

VERDICT: REPAIR
