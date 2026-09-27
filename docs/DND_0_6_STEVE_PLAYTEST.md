# D&D 0.6 Steve Playtest Evidence

Run date: September 26, 2026 (Steve local time, America/Chicago).

## Results

- Deterministic full-game smoke: **won** in the Hollow Vault after 9 player
  inputs and visiting 5 rooms; the brass ring persisted into the Gallery, Mira
  opened the west shortcut, and the hero reached the final encounter.
- Full-game narrator smoke: `mlx-community/Qwen3.5-9B-MLX-4bit`; 17 model
  requests, 0 fallbacks, 14 scenery objects accepted and 1 rejected. Latency
  averaged 8.892 seconds (median 8.667 seconds; maximum 15.505 seconds).
  Session `d8b998a744af463ba70a69a878e93fee` ran 151.5 seconds end-to-end.
- OptiQ live D&D narrator smoke: `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit-REAP-19B`;
  one real NPC-dialogue request completed in **22.067 seconds**, within the
  configured 24-second timeout, with **no fallback**. Python independently
  resolved the ring reaction and opened the shortcut before narration.
- The OptiQ response stayed consistent with the resolved action. The longer
  9B run also embellished some scene details beyond supplied facts; treat that
  as a playtest observation for future narrator-quality review, not as game
  state. Mechanics and exits remained Python-authoritative.

## Session evidence

- Full 9B JSONL: `~/.local/state/dnd-bot-interface/sessions/20260926T190236-0500_d8b998a744af463ba70a69a878e93fee.jsonl`
- OptiQ JSONL: `.dnd-sessions/20260926T190710-0500_b484f05e2b3b4169a3bdbc37af9fd9f1.jsonl`
- `.dnd-sessions/` is ignored by Git; runtime play data stays local.
- Inspect the latest session with `python3 -m dnd_combat report`.

## Steve runbook

From the repository root:

```sh
# Deterministic play
python3 -m dnd_combat

# Existing local OpenAI-compatible service; no service restart required
export DND_NARRATOR=local
export DND_LLM_ENDPOINT="http://127.0.0.1:8080/v1/chat/completions"
export DND_LLM_MODEL="mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit-REAP-19B"
export DND_LLM_TIMEOUT=24
python3 -m dnd_combat

# Review the latest recorded play
python3 -m dnd_combat report

# Run the deterministic suite
python3 -m unittest discover -v
```

The 24-second default is environment-configurable through `DND_LLM_TIMEOUT`.
Steve's measured Qwen3.5-9B generation speed was 10.736 tokens/second; the
180-token room-object budget alone implies about 16.8 seconds of generation,
so 24 seconds allows additional request and first-token overhead while retaining
the deterministic fallback path.
