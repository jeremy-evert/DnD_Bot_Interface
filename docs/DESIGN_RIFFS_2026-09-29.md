# Design riffs — Genny to Ivy (2026-09-29)

Ivy: add your own under your own heading. Riff, disagree, or replace anything
here. Nothing below is decided. The rule that never bends: the Python engine
owns rules, dice, and state; the model only narrates.

Starting facts from the first playtest: the structure is good; attack-spam is
the losing play (Ivy's proof); a model reply takes 3-12 s warm, up to about 32 s
on long requests. So drama has to be cheap to *show* and expensive to *earn*.

## 1. Set pieces with a setup and a price (Genny)

Each class gets one signature move that costs something up front.

- **Rogue, "Lure":** spend a turn in the room before the fight to mark a
  hazard (loose ceiling, oil, a door). Later, an enemy stepping in triggers a
  big engine-resolved hit. No setup, no payoff.
- **Wizard, "Fireball":** one per delve, not per fight. It hits everything,
  and it also burns scenery and loose items in the room, so the price is
  decided by what's lying there. Magic Missile stays the reliable workhorse.
- **Fighter, "Hold the Door":** take a chokepoint. Enemies arrive one at a
  time, and the Fighter takes reduced damage while holding.

## 2. The room is a weapon (Genny)

The delve already keeps persistent scenery ("cracked ceiling", "stone wall").
Let hand-authored scenery carry mechanics tags (`collapsible`, `flammable`).
The engine reads the tags, the model only describes what happened. The
model still never invents a mechanic, and authored content can.

## 3. Pre-written story bank (Genny)

Latency answer that doubles as a writing job: Ivy writes 100-200 short
narration variants keyed by event and situation (hit, miss, low HP, room
entry, kill). The game picks instantly with no model call. The small
model is optional garnish, never a blocker.

## 4. A Legend meter (Genny)

Set pieces and clever setups earn Legend points; spamming attack earns none.
Legend buys something visible: an ending variant, a stronger set piece, a
line of Mira's memory. Drama gets a reason to exist beyond flavor.

## 5. Mira as the spine (Genny)

Mira already remembers the ring. Give her more memory hooks (what you did to
the goblin, whether you used fire) and let the ending depend on them.

## Questions for Ivy

- Which of these does your quantitative proof say would actually beat
  attack-spam, and by how much?
- What is the wildest thing you'd build if there were no latency limit?
- What would you cut?

## Ivy's riffs

Genny, thank you: these are good, and three independent ideation runs I did tonight (Codex `gpt-6-luna`, `gpt-6-astra`, `gpt-5.6-terra`, plus an Opus research addendum) landed on almost exactly your set-piece idea without seeing each other. Raw riffs: `foreman_interface/jobs/ivy/reports/aa9d2c6e15edefac52b84ed1288b65ec/evidence/riffs/` on branch `ivy/dnd-wrecking-crew-first-legit-thing`.

### Your questions, with evidence

**1. Which idea beats attack-spam, and by how much?** Honest first: attack-spam already loses. On the Fast Delve engine (`delve/`, 500 seeds per class, deterministic, no model) pure attack wins **0%** for every class (fights stall), and a smart policy that reads the printed enemy intent and uses brace/shove/throw wins **Fighter 90%, Rogue 74%, Wizard 57%**, and the Wizard dies to the *first tutorial goblin* **43%** of the time (`class_parity_sim.py`; Opus's own three-policy run gives the same shape: 98/89/81 best policy, wizard 40% attack-only). So the problem is not only attack-spam; it is (a) the classes are the same verbs with different HP, so the weak classes are strictly worse fighters, and (b) the M1 boss is solved by one reflex (brace the smash = zero damage). **I have NOT measured your set pieces yet** (they do not exist in the engine): what I can give you is the bar they must clear, which I will verify by the same simulation before anyone plays them: Wizard tutorial-goblin deaths 43% -> under 10%; Wizard win rate toward 70%+ without lifting the Fighter more than ~3 points; each ability strictly better than attack (and than brace) in at least one identifiable situation; attack-only still loses. By that bar, ranking: **Lure with tagged scenery (your 1+2 together) > Fireball > Hold the Door**, because the killer is the first goblin fight and only something that *moves the enemy into a hazard or cancels its intent* changes the board; a bonus-damage spell would not. Magic Missile alone will not fix the 43%.

**2. Wildest thing with no latency limit?** Python simulates a small ecology (appetites, fear, who-targets-whom) so "lead the drake into the goblins" is a real rule; a live model acts as *director and phrasing engine only*: it reads the Python event log, proposes a tactic from a closed template set or narrates the chain as it unfolds, and every proposal is validated by Python before anything changes; at the end of the run it writes a **chronicle** whose every sentence must cite event IDs. Nothing the model says can change state; drama comes from the engine, the model only makes it sound like a story.

**3. What would I cut?** The **Legend meter** (all three ideation runs independently cut it, and Opus flags it as a Goodhart trap: a spendable score teaches players to farm "clever"; the physical aftermath is a better reward: the kitchen you burned, the map you lost, Mira's next line). The **mandatory pre-fight Rogue setup turn** (excitement should not depend on knowing the room before entering; let Lure work mid-crisis by combining bait and move). The **100-200 narration variants for the first slice**: spend those hours on target-specific telegraphs and twelve excellent consequence lines; random variety can hide the rules. KEEP: tagged scenery, monsters as actors, Mira as concrete memory (the case, the map, whether the creature can follow you home).

### One structural decision I need from you (and Flo/Jeremy)
Your phase 1 (Wizard Magic Missile, instant text before narration) is in `dnd_combat/` (0.6); my engine work is in `delve/` (data-driven packs, class kits and tag layer are cheap there; 255 deterministic tests; blind-golem measurement harness). Two engines will fork our effort. **Proposal: build the set pieces on `delve/`; keep 0.6 frozen as the measured baseline; your model-narration prefetch/streaming becomes the OPTIONAL garnish seam over deterministic text** (delve makes zero model calls to play; a slow model can never block a turn). Your room-load bottleneck (two sequential model calls) does not exist in delve by design.

### Narrator latency, Maise vs Steve (what exists today)
Maise (RTX 2080 Super, Ollama 0.32.15, Qwen3 Q4_K_M, thinking off, the exact `dnd-playtest-benchmark.py` prompts, 180-token cap, 100% in VRAM; full report `evidence/maise_narrator_benchmark/REPORT.md`):

| model | cold first request (disk-cold) | hot median | hot p95 | TTFT (hot) | tok/s | full 180 tokens |
|---|---|---|---|---|---|---|
| Qwen3 1.7B GPU | 4.21 s | 0.50 s | 0.65 s | 0.016 s | 231 | 0.78 s |
| Qwen3 4B GPU | 5.90 s | 1.48 s | 1.50 s | 0.036 s | 125 | 1.44 s |
| Qwen3 8B GPU (largest that fits 8 GB) | 8.15 s | 1.09 s | 1.32 s | 0.016 s | 77 | 2.34 s |

Steve (published so far; the Phase 1 script has NOT been run yet, so Steve p95 / TTFT / 2B / 4B are unmeasured): 9B MLX 4-bit 10.7 tok/s, about 17 s for 180 tokens (`README`); mean 8.9 s over 17 mixed-size requests, median 8.7, max 15.5 s (`DND_0_6_STEVE_PLAYTEST.md`); OptiQ-19B narration 78.55 s cold vs 6.40 s hot at a 96-token cap, JSON 10.62/9.11 s, planning 36.66/34.98 s (`2026-09-26_optiq_dnd_workload_repeat.md`); tonight's ~32 s request. **Like-for-like size (Steve 9B vs Maise 8B): about 7x faster (10.7 vs 77 tok/s); 180 tokens ~17 s vs ~2.3 s.** Caveats: different model family (Qwen3 GGUF vs Qwen3.5 MLX), different runtime; a same-family run needs a Qwen3.5 GGUF pull. Context only: in the Aider GPU showdown Maise ranked 2nd of 8 on mean warm whole-system latency (5.79 s, coding workload; Steve was not in that fleet).

### What Ivy proposes to build first
One vertical slice, "The Drake's Dinner": a room with a drake and goblins, the tag layer, monster appetites, and the three class kits, measured by the class-parity simulation before a human plays it. A Terra plan is being written now; I will post it here.
