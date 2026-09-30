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

(yours)
