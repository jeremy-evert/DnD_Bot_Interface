# D&D 0.3.1 — Qwen latency and thinking correction

> Historical status: **reconstructed** from the live Qwen playtests and resulting 0.3.1 patch.

The first live run produced no visible DM lines because narrator calls timed out. A direct benchmark showed the 2B Qwen model could produce a short useful response in roughly three seconds, while the 9B model was too slow for a four-second gameplay timeout.

Correct the narrator boundary without changing game authority.

Requirements:

- explicitly disable Qwen thinking for narration requests
- use the small local Qwen model for short narration work
- keep narration concise
- preserve deterministic text even when narration is enabled
- expose optional debug information when narrator fallback occurs
- timeout/failure/malformed output must fall back cleanly
- do not alter combat or world-state authority

The LLM should be seasoning, not a mandatory step after every sword swing.
