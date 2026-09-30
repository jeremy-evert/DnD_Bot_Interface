# Genny process log

One entry per work unit: what was done, who did it, what was checked, what it
cost, what worked. Spend is recorded as unknown where no number exists;
nothing here is estimated.

## 2026-09-29

| Unit | Done by | Independent check | Helpers/dispatches | Spend | Notes |
|---|---|---|---|---|---|
| Steve narrator benchmark (2B/4B/9B cold-hot + narrator runs) | Genny | Receipts in mlx_server/.runtime | none | unknown (session tokens only) | Confirmed slow 9B; 2B about 3 s. |
| Warm-coexistence test (2B+4B+9B interleaved) | Genny | none | none | unknown | RSS only, undercounts GPU memory. |
| Magic Missile + instant text (6a53025) | Genny | own tests only; no Sol pass | none | unknown | Departs from Terra/Luna/Sol routing in GENNY_GOBLIN_FOREMAN.md. Should be re-examined by a Sol pass. |
| Design riffs doc | Genny | none | none (Ivy invited, no reply yet) | unknown | Wrote alone; wanted Ivy's input. |

## What is not working

- No helper or subagent has been used yet. Doctrine says Goblin work goes through the crew; this session skipped it.
- No spend tracking exists. Next step: record each dispatch's model, tier and cost here as it happens.
