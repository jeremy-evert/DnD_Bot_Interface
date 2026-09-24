# Prompt archive

This directory preserves the development missions that shaped the project.

The early prompts were originally issued conversationally and were not committed to the repository. Where the exact historical wording was unavailable, the prompt is clearly marked **reconstructed** and preserves the milestone's actual behavior and constraints from the repository/commit history.

## Current mission

`CURRENT` points to the prompt launched by `../scripts/hanna`.

Current target: **D&D 0.5 refactor checkpoint**.

## Milestones

| File | Milestone | Provenance |
| --- | --- | --- |
| `01_DND_0_1_COMBAT.md` | Small deterministic combat loop | Reconstructed |
| `02_DND_0_2_DUNGEON.md` | Three-room adventure | Reconstructed |
| `02_5_DND_0_2_5_PLAYABILITY.md` | Human-playtest polish | Preserved from issued mission |
| `03_DND_0_3_QWEN_NARRATION.md` | Optional local LLM narrator | Preserved from issued mission |
| `03_1_DND_0_3_1_QWEN_LATENCY.md` | Non-thinking/latency correction | Reconstructed from live playtest |
| `04_DND_0_4_ROOM_OBJECTS.md` | Persistent room objects | Preserved from GitHub Issue #3 |
| `05_DND_0_5_REFACTOR.md` | Architecture checkpoint | Current mission |
| `06_DND_0_6_MAP.md` | Map expansion | Planned, do not run early |

## Launch

From the repository root:

```sh
./scripts/hanna
```

To explicitly launch another archived mission:

```sh
./scripts/hanna prompts/06_DND_0_6_MAP.md
```

The launcher refuses to start from a dirty working tree, fast-forwards from GitHub, and gives Codex the selected mission plus the repository-level `AGENTS.md` rules.
