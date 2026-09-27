# Wilbur's Workbench — D&D worksite

This directory holds the D&D project's planning/evaluation artifacts for the Brenda experiment.

The roles are deliberately separate.

```text
project truth
    ↓
Penny
plans ONE bounded build unit
    ↓
Brenda
builds only that unit
    ↓
Sandy
compares Penny's contract with Brenda's result
    ↓ FAIL
Annabelle
locates the correction
```

## Ownership

- `PENNY_PILE.md` belongs to the D&D project. It stores big build directions, not executable Brenda tasks.
- `penny/units/` stores individual bounded work units authored by Penny.
- `sandy/` stores independent PASS/FAIL evaluations when we begin preserving them in-repo.
- `annabelle/` stores local architectural correction records when Sandy has proved a failure.

Runtime Brenda receipts do **not** belong here by default. Brenda owns runtime evidence under her external state root so failed worktrees can be destroyed without destroying the evidence.

## Hard boundaries

Penny may read broadly enough to plan against current project truth.

Brenda receives only one bounded unit.

Sandy evaluates only whether Brenda satisfied Penny's unit.

Annabelle is invoked only after failure to determine where a correction belongs.

Broader fleet/process diagnosis remains outside these roles for now.
