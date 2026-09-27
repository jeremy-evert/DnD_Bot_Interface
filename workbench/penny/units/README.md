# Penny work units

Penny writes one JSON work unit here at a time for Brenda.

A unit is executable instruction, not project planning.

Required shape:

```json
{
  "unit_id": "dnd-...",
  "goal": "one bounded implementation responsibility",
  "read_paths": ["..."],
  "write_paths": ["..."],
  "proof_commands": ["..."],
  "max_model_steps": 10,
  "base_ref": "HEAD"
}
```

Rules:

- one separable responsibility;
- exact scope;
- explicit proof;
- no architecture exploration delegated to Brenda;
- no vague "improve", "refactor", or "make better" goals;
- tests are part of the contract;
- if current truth makes the pile item wrong, Penny updates the plan rather than forcing Brenda through stale instructions.
