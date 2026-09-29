# Quality Vision: The Mossy Delve

**What "good" means, how to tell whether we are getting there, and where the game could go**

- **Status:** a standing design and measurement reference for `DnD_Bot_Interface` (The Mossy Delve, D&D 0.6 at `main` `94af79a`) and for the Ivy wrecking-crew playtest harness (`terra-dnd-playtest-measurement-01`).
- **Author:** Opus (a research dispatch for Ivy), 2026-09-28.
- **Authority:** this is advice and a yardstick. It changes no code and makes no decisions. Where it disagrees with an existing plan, the disagreement is stated so a human can settle it.
- **Evidence convention:** claims marked **[S#]** point to a row in the Sources table (section 10). **[lore]** means practitioner lore I could not tie to a primary source. **[synth]** means my own synthesis. **[obs]** means something I checked directly in this repository on 2026-09-28 by reading code or running a read-only probe.

---

## 1. Executive summary

### What "great" means for this game

A student who does not care about D&D sits down at a terminal. Within two minutes they are doing something, not reading about it. Within five, they notice something odd: a bell with no clapper, a compass that doesn't point north, an archivist who wants a ring. They form a guess. They act on it, sometimes clumsily. The world answers at once, fairly, and remembers what they did. They fail at least once, and the failure costs them something *and teaches them something*. Near the end they carry out a plan they made themselves, using things they chose to pick up and facts they worked out, and they can tell what difference it made. When the facilitator says "you can stop now," they don't. Afterwards they tell the story in the first person, with "because" in it.

That is the bar. Prose volume isn't. A clever LLM sentence isn't. "The world remembers" isn't enough by itself either: memory the player can't perceive or can't use counts for nothing.

### The seven principles, in priority order

1. **Legible consequence.** Player choices change Python-owned state, the change shows up where the player can perceive it, and it matters later. (The project's own thesis, `PLAY_DESIGN.md`: "a consequence generator".)
2. **Curiosity gaps that pay off.** The game repeatedly opens small, specific questions the player can almost answer, and it *closes every one it opens* through play, not through exposition.
3. **Momentum: the Doom principle.** Keep the time and effort between intent and meaningful feedback tiny: few keystrokes, no dead waits, no reading walls, readable spaces. For a player who isn't invested yet, this gates everything else.
4. **Interesting decisions under uncertainty.** Choices have trade-offs, depend on the situation, and have outcomes the player can foresee in outline but not in detail. There is no dominant option.
5. **Failure that moves.** Failing costs something and changes the situation. It never means "nothing happens", and it never means "the run is over and you learned nothing".
6. **A truthful voice.** Every word the player reads, from Python or from the LLM, is consistent with the state. Generated texture reflects state instead of just decorating it. The narrator never invents, flatters, forgets, or steers.
7. **Identity and attachment.** Over time, the player becomes somebody here: a remembered history, relationships, a recognizable style.

### Why this order

- **Consequence comes first** because it is what the architecture guarantees and a free-form LLM cannot. RPGBench found that current models "often struggle to implement consistent, verifiable game mechanics" even while they produce engaging stories [S31]. The authoritative engine is this project's moat. If consequence is weak, every other principle becomes decoration.
- **Curiosity comes second, not first,** even though "did I want to see what happens next?" is the north-star metric. Curiosity depends on consequence. An information gap that never closes teaches the player that gaps are noise, and Nelson lists "not to be given too many red herrings" among the player's rights [S14].
- **Momentum ranks third, above decisions,** because of who is playing. For a student who has not bought in, a two-step `move` → `Direction:` prompt, a 9-second narrator pause, or a refused `north` ends the session before any decision gets made. Momentum is a *floor*, not a goal: past a threshold, extra speed buys little. So it is measured as a budget, not a score (section 5).
- **Decisions and failure** are the content of the loop, and they follow directly from 1–3.
- **Truthful voice ranks sixth** because this architecture already contains most of its risk: Python owns truth, and P-002 hardened the narrator boundary. It is still a principle because the LLM's remaining failures (invention, flattery, oatmeal) directly damage 1 and 2.
- **Identity comes last** only because it needs play time the current 10-room game doesn't provide. It is the most likely thing to bring a student back for a *second* session.

### What this means for the current build (a calibration example)

Applying these principles to 0.6 as it stands is the fastest way to show what the yardstick does. These are **[obs]**, checked read-only against `main` on 2026-09-28:

- **The vault doesn't need Mira.** `Rootbound Shrine` has an open `east` exit to `Hollow Vault` (`world.py`). The ring-for-Mira arc, the one memory payoff the design celebrates, saves exactly one move (gallery → west → vault instead of gallery → east → shrine → east → vault). This is a textbook *hollow consequence* (mode C-3 below). The Steve smoke win "after 9 player inputs visiting 5 rooms" is consistent with that.
- **The shrine's text says "sealed vault"**, but the east exit into the vault works. That is a deterministic-text contradiction of the kind `WORLD_STATE_CONTRADICTION` is meant to catch, and the harness should have a fixture for it.
- **At the main prompt, `north` and `n` are unrecognized, and `s` means *status*.** Parser-IF players expect `s` to mean south. This is a convention clash at turn 1 (mode L-2).
- **Four takeable objects are never read by any rule:** clay cup, silver leaf, offering bowl, brass nameplate. Two visible mysteries are never paid off: the clapperless bell and the stone compass that "points toward no obvious north". So Hypothesis B ("carried junk can become interesting") is currently unfalsifiable, because nothing in the engine can notice junk.
- **Class is a stat block.** Fighter, rogue, and wizard have identical verbs; the wizard has no spells. That is a choice illusion at character creation, the very first decision the player makes.
- **Combat offers attack, potion, or status,** and there is no retreat. Attack is the dominant action on nearly every turn, so by Meier's test these aren't interesting decisions [S5].
- **Death prints "The adventure ends here."** Nothing carries over. That is fail-with-nothing.
- **Live narration averaged 8.9 s per request** (Steve playtest, 17 requests). With a room-entry narration and a scenery request per new room, the first trip through the dungeon includes something like a minute or more of waiting. That violates the Doom principle outright.

None of this is a criticism of the milestone discipline. 0.6 was scoped as a map experiment. The point is that the yardstick finds the highest-leverage problems from a transcript and a read of the content graph, before any golem runs.

---

## 2. Theory synthesis

For each principle below: what the research or craft literature says, where it comes from, what it implies for a deterministic terminal engine whose LLM cannot own state, and where the sources disagree.

### P1. Legible consequence

**Sources.**
- Sid Meier's GDC 2012 talk puts *persistence* on the list of what makes a decision interesting: a decision should affect play for a meaningful duration. It also names *information*: the player needs enough knowledge to choose comfortably, and Meier says it is "almost worth erring on the side of providing the player with too much information" [S5].
- Tynan Sylvester's "The Simulation Dream" argues that players never perceive the simulation, only the mental model it projects: "The whole value of a game is in the mental model of itself it projects into the player's mind" [S19]. He cites Richard Garriott on *Ultima Online*'s ecology simulation, which "literally no-one ever noticed" and was eventually removed [S19].
- MDA sets up the same asymmetry. Designers work from mechanics up, while players meet aesthetics first; they only encounter mechanics through dynamics [S1].
- The project's own `PLAY_DESIGN.md` states it most compactly: "The player did something. The world remembers. That memory matters later."

**Implication.** Python-owned state that no output ever reveals, and that no later rule ever reads, is invisible and therefore worthless as design, however correct it is. Legibility is a property of the *rendered transcript*, not of the snapshot. That makes consequence measurable in a way curiosity isn't. A consequence exists only if (a) a player decision writes a state field, (b) a later rule *reads* that field, and (c) the output around the read makes the causal bridge perceivable. The engine can instrument (a) and (b) mechanically. The quote-gated judge checks (c).

**Where the sources disagree.**
- Sylvester leans on *apophenia*: keep the systems simple and let players project meaning onto ambiguous events [S19, S20].
- James Ryan's dissertation, *Curating Simulated Storyworlds*, argues the reverse: without *curation*, emergent storyworlds don't yield stories at all, and systems must actively sift and recount what happened [S21].
- For a 10-room game with a small narrator, I side with Ryan **[synth]**. Our world is too small for apophenia to find much, and a narrator that retells causal chains grounded in event IDs is exactly the kind of curation the architecture permits. Sylvester's point still stands as a warning: don't build hidden simulation depth the player can't see.

### P2. Curiosity gaps that pay off

**Sources.**
- Loewenstein's information-gap account treats curiosity as a cognitively induced deprivation that arises when attention focuses on a gap in one's knowledge [S2]. It predicts that curiosity is *low when you know too little* and *low when you know nearly everything*, and peaks in between.
- Kang et al. (2009) tested that inverted-U relation between curiosity and confidence with trivia questions. They found curiosity correlated with activity in reward-anticipation regions, and higher curiosity went with better recall of surprising answers one to two weeks later [S3].
- The Alexandrian's Three Clue Rule is the craft counterpart: "For any conclusion you want the PCs to make, include at least three clues," because a single clue is a chokepoint that the player can miss, fail to recognize, or misread [S9].
- Graham Nelson's *Craft of Adventure* bill of rights includes "Not to be given horribly unclear hints", "To be able to understand a problem once it is solved", "Not to be given too many red herrings", and "To have a good reason why something is impossible" [S14].
- Schell's *Art of Game Design* includes lenses for curiosity and surprise [S7]. I confirmed they exist but not their exact questions.

**Implication.** A curiosity gap is a contract with the player:
- *Opening* it is cheap. "A bell with no clapper" is an opening.
- *Keeping it at the right distance* is design: the player should be able to form a hypothesis.
- *Closing* it is mandatory: a later state read, NPC line, or mechanical effect has to answer it.

In this architecture, Python must own the *answer* before the question is asked. `PLAY_DESIGN.md` already warns that the model "should not be allowed to quietly rewrite hidden truth". The LLM can phrase clues, but only from fact atoms Python has already committed, and those atoms must exist before the first clue is shown. Every visible anomaly in the content (anything described as missing, broken, pointing wrong, or silent) is an open gap and must be registered with a payoff. That makes open loops *statically auditable*: an unanswered anomaly is a content bug detectable without any playtest (mode K-1).

**Where the sources disagree.**
- Meier says err toward too much information [S5]. Loewenstein says a gap is what drives curiosity [S2]. The OSR tradition treats hidden information and "player skill, not character abilities" as the core pleasure [S10].
- The reconciliation that runs through the better sources is **[synth]**: *be transparent about rules, stakes and threats, and opaque about world facts.* Blades in the Dark makes clocks explicitly visible ("A clock is like a speedometer...") [S11]. Into the Breach telegraphs every enemy attack so each loss feels like the player's own fault [S27]. Both keep the world's secrets hidden. The Delve should never hide *how dangerous something is*. It should hide *why the keeper wore a ring*.

### P3. Momentum (the Doom principle)

**Sources.**
- Csikszentmihalyi's flow conditions include clear goals, immediate feedback, and challenge matched to skill [S4]. Sweetser and Wyeth's GameFlow model turns these into eight evaluation elements: concentration, challenge, player skills, control, clear goals, feedback, immersion, and social interaction [S8].
- Doom is the practitioner's case study. Romero's level rules, as collected by the Doom Wiki and quoted in eevee's essay, include "making my levels flow so the player will revisit areas several times", "creating easily recognizable landmarks in several places for easier navigation", contrast "between light and dark areas, cramped and open areas", "making sure that if a player could see outside that they should be able to somehow get there", and "several secret areas on every level" [S23].
- id's 2016 reboot was built on "push forward combat": regenerating health, reloading and cover were removed so that players "[take] what they need from enemies" [S24].
- Doom's content was separated from its engine in WAD files, which let players "design new levels, change graphics and sounds" without touching the executable. The source followed in December 1997 under a restrictive license and was relicensed under the GPL in October 1999 [S25].
- Nelson's rights include "Not to need to do boring things for the sake of it", "Not to have to type exactly the right verb", and "To be allowed reasonable synonyms" [S14].

**Implication.** Doom's essence, translated for a text game **[synth]**:

- **Speed:** turn latency under about a second for everything except rare, earned, live-generated moments.
- **Tactile feedback:** every input produces a distinct, specific, state-bearing response.
- **Readable space:** landmarks, loops, visible-but-not-yet-reachable places, and secrets.
- **Risk/reward pull:** resources are regained by acting boldly, not by waiting.
- **Moddability:** the world is data that other people can author.

This turns into a *friction budget* per session (section 5), not a quality score. It also rules out the current live-LLM-per-room pattern. The owner's instinct, pre-generate most narration and go live only for genuinely novel moments, is correct on these grounds as well as on hardware.

**Where the sources disagree.**
- Flow wants clear goals and continuous competence. Curiosity wants unresolved gaps. OSR wants danger and the chance of sudden loss. A game tuned purely for flow drifts toward a treadmill **[synth]**.
- Doom itself shows the resolution: fast, fluent verbs in a space full of secrets and threats. Flow belongs to the *interface and the verbs*, uncertainty to the *world*.

### P4. Interesting decisions under uncertainty

**Sources.**
- Meier's criteria: trade-offs, situational decisions ("ideally it acts in an interesting way with the game situation"), personal expression, risk versus reward, short versus long time horizons, persistence, and adequate information. His negative test is that if a player always picks the same option, or picks randomly, the decision isn't interesting [S5].
- Matt Finch's OSR primer: "Rulings, not rules", and "Player skill is more important than character abilities" [S10].
- The Alexandrian's "Xandering the Dungeon" argues that linear dungeons eliminate "the players' ability to make meaningful strategic choices". Loops, multiple entrances, and secret paths let each group make the dungeon its own; Jaquays's *Caverns of Thracia* is the exemplar [S12].
- Sam Kabo Ashwell's taxonomy of choice-game structures (Gauntlet, Branch-and-Bottleneck, Open Map, Floating Modules, Loop-and-Grow...) gives vocabulary for where choices actually diverge and where they converge [S15].

**Implication.** A decision needs (a) at least two options, each best in *some* reachable situation; (b) a cost the player can see; (c) an outcome the engine resolves deterministically but that the player can't fully predict. The current Delve map has a loop (crossroads–gallery–shrine–rootway–cistern), which is good, Jaquays-style. But the only costs in the game are HP and a single potion. Nothing costs *time*. So "detour for the star chart" (terra_plan2) is, as Terra honestly notes, "not yet a hard tradeoff". A clock is the cheapest fix (Blades [S11]; direction D-3 below).

**Where the sources disagree.**
- Meier's "too much information" versus OSR's deliberately hidden risk, as above.
- Bartle's types [S16] suggest different players want different decision kinds. Yee's survey of MMO players found motivations clustering into *achievement, social, immersion* components [S17], an empirical rather than typological model. To my knowledge, Yee has argued these motivations aren't mutually exclusive types; I didn't re-read that part.
- For a classroom, assume a mix. Every scene should offer one decision a tactician enjoys and one an explorer enjoys **[synth]**.

### P5. Failure that moves

**Sources.**
- Dungeon World's GM moves are made "when the players look to you", when they "give golden opportunities", and after a miss. A 7–9 result is success with a cost or complication. Soft moves warn, hard moves bite, and ignored soft moves become hard ones. Among the listed moves: "show signs of an approaching threat", "reveal an unwelcome truth", "offer an opportunity, with or without cost", and "tell them the requirements or consequences and ask" [S13].
- Zarf's Cruelty Scale classifies games by whether you can get stuck and whether you'd *know*. "Cruel" means you can reach an unwinnable state that isn't obvious even afterwards [S22].
- Nelson: "Not to be killed without warning" and "Not to have the game closed off without warning" [S14].
- Dwarf Fortress's unofficial motto, "Losing is Fun", reflects a game with no victory condition, where collapse is the story [S26].
- The Berlin Interpretation lists permadeath as a high-value roguelike factor, paired with a randomized world that makes starting over interesting rather than punishing [S28].

**Implication.** Fail-forward in this architecture means **Python** chooses and applies the consequence from a finite, authored table (noise, clock tick, lost item, exposed information, NPC attitude shift, route closure). The LLM only narrates it. Death can stay permanent, as roguelikes argue it should, *only if* something carries over: knowledge, a legacy, or a chronicle. Otherwise it is Nelson's "killed without warning" with extra steps.

**Where the sources disagree (sharply).**
- Critics of fail-forward argue it "destroys the joy of having different possible outcomes" and works as "a railroading tool", because labelling one direction "forward" means the GM is steering [S29].
- The Alexandrian uses failing forward selectively, for example turning a failed information-gathering check into a lead on where the information can be found [S30]. That is not a universal rule.
- My position **[synth]**: failure must *change the situation*, but it must not secretly deliver the success anyway. "The door stays shut, the patrol heard you, the clock ticks" is real failure that moves. "You fail to pick the lock but notice a key" is disguised success. The first is the target; the second is a mode (`FAIL_FORWARD_FAKE`, family F).

### P6. A truthful voice

**Sources.**
- Emily Short's "Bowls of Oatmeal and Text Generation": generation is "purely decorative unless it is tightly correlated with gameplay — and the player will soon realize that it is decorative and start looking past it" [S34].
- Kate Compton's "10,000 bowls of oatmeal": mathematically unique outputs can all be *perceived* as the same; "Perceptual uniqueness is the real metric" [S33].
- On LLM failure modes:
  - RPGBench: strong narrative, weak rule and state enforcement [S31].
  - Sharma et al.: RLHF-trained assistants consistently show sycophancy across free-form tasks, and the paper traces this partly to human preference data that favors agreeable responses [S35].
  - Liu et al., "Lost in the Middle": models use information at the start and end of a long context better than information in the middle [S36]. This mechanism produces "amnesia" in long prompts.
  - FIREBALL: LLMs given true structured game state produce better D&D turns than ones given dialogue history alone [S37].
  - CALYPSO found that LLMs are more useful as DM *assistants* than as sovereign DMs [S38].

**Implication.**
- The architecture already gets the hard part right: facts in, prose out, Python output always printed first.
- What's left is *decoration without correlation* and *invention*. Terra_plan2's narration bank uses a closed abstract vocabulary that forbids names, numbers and directions. That will prevent contradictions, but by Short's argument it is decorative *by construction*, and players will learn to skip `DM:` lines. The fix isn't to loosen validation. It is to key bank variants on *state* as well as event and room: enemy dead or alive, Mira asked or not, the player hurt, a clock at 3/4. Texture then carries information and stops being oatmeal.
- The narrator's system prompt already says "Keep the tone vivid, playful". For an 8B–9B model, that plus sycophancy pressure predicts narration that flatters misses ("you deftly..."). Section 3 has a mode for it.

**Where the sources disagree.**
- The agentic GM study (Jørgensen et al.) reports that a multi-agent GM *improved* immersion and curiosity over a simple prompted one [S32]. Architecture helps.
- RPGBench says rule enforcement remains weak regardless [S31].
- Both are consistent with the project rule: give LLMs more *creative* responsibility over time, and never more *state* authority.

### P7. Identity and attachment

**Sources.**
- Self-determination theory applied to games (Ryan, Rigby & Przybylski 2006): perceived in-game autonomy and competence, and relatedness in multiplayer, independently predicted enjoyment and future play [S6].
- Short's salience-based and quality-based narrative structures [S39], and Kennedy's later reframing as "resource narrative" [S40], are the craft of making content respond to accumulated player history.
- Hades is the commercial demonstration: about 21,000 recorded voice lines, organized so characters react to what the player has done and don't repeat [S41].

**Implication.** Attachment needs *many small acknowledgments of history*, which is exactly what a pre-authored, state-keyed bank delivers cheaply (direction D-1). NPC memory should be a small structured record, as `PLAY_DESIGN.md` already specifies, never a transcript fed to a model.

**Where the sources disagree.** Kennedy regrets treating all qualities as "created equal", because it "erases too many potentially useful distinctions" [S40]. Our storylet state should distinguish spendable *resources* (potions, time, favor) from *story facts* (Mira asked, keeper's secret known). The two need different validation and different UI.

---

## 3. Failure-mode taxonomy v2

### Critique of the current 14 modes

The terra_playtest taxonomy is sound in its discipline (finite, quote-gated, fixture-backed), and v2 keeps all 14 modes. Its weaknesses:

1. **`CHOICE_EQUIVALENCE` will almost never fire as defined.** It requires identical *canonical state* after two alternatives. But "take chart" versus "leave chart" always differs in inventory, so the detector reports a real choice even when nothing ever reads the chart. It should compare an **outcome projection**: the state fields that some later rule actually reads, plus terminal outcome, reachable-room set, and NPC lines emitted. Instrument reads with a read-set tracer in the harness: wrap `Adventure` field access in replay (**[synth]**, but mechanically straightforward). A state field no rule ever reads is dead state.
2. **`NO_CONSEQUENCE_STALL` misses meaningless state changes.** `take clay cup` changes inventory, so it isn't a stall, yet it is exactly the problem. v2 adds *Dead-weight item* (C-4).
3. **`WORLD_STATE_CONTRADICTION` only targets narration.** Static room descriptions already contradict state ("sealed vault", **[obs]**). The fact-to-text rules must run over *all* rendered text, including `look` output and banked `DM:` lines.
4. **There are no LLM-specific modes,** even though the narrator is the biggest known source of invention (the Steve 9B run "embellished some scene details beyond supplied facts").
5. **There are no pacing or latency modes that a script can measure.** `PACING_DRAG` is judge-only. Wall-clock time is fully observable.
6. **`UNRECOGNIZED_COMMAND` weights every miss equally.** A refused `north` (a universal convention) is far worse than a refused `cast fireball` (off-menu, understandable). v2 splits these.
7. **Nothing detects open loops or hollow payoffs.** The two most important curiosity failures are content-graph properties and can be found statically, before any golem plays.

### How to read the tables

- **Sev** keeps Terra's 1–5 weight scale, reasoned by which principle a mode breaks. Modes that break P1 or P2 (the core loop) weigh 4–5. Friction modes weigh 2–3, except where they end sessions.
- **Detect** says who can flag an instance: *M* is a mechanical detector over transcript and snapshots; *S* is static analysis of content or code, with no play; *J* is the quote-gated judge; *H* is humans only.
- **FP** summarizes false-positive risk.
- Existing modes keep their names; new ones get a family code.

#### Family C: Consequence (P1)

| Mode | Definition | Theory | Observable signature | Sev | Detect | FP risk |
|---|---|---|---|---|---|---|
| `NO_CONSEQUENCE_STALL` (existing) | A valid non-query action changes neither state nor actionable information. | Meier persistence [S5]; PLAY_DESIGN | State hash unchanged, output not a query, action not in the known-invalid set. | 4 | M | Low. Exclude deliberate "wait/listen" verbs when they exist. |
| `CHOICE_EQUIVALENCE` (revised) | Two alternatives from the same prefix and seed produce identical **outcome projections**. | Meier; Ashwell bottlenecks [S15] | Counterfactual replay where the diff over the read-set projection, terminal state, reachable rooms, and emitted NPC lines is empty. | 4 | M | Medium. Some equivalence is intended (flavor choices). Allow a declared `flavor_only` tag, which must itself be reported. |
| `CONSEQUENCE_OPACITY` (existing) | An outcome depends on an earlier choice, but no rendered text bridges them. | Sylvester mental model [S19] | Read-set tracer shows field F (written at turn t1) read at t2, and no output in [t2, t2+1] mentions F's referent. Judge quotes both. | 4 | M+J | Medium. A bridge can be implicit but clear. Judge quote-gates it. |
| **C-1 `DEAD_STATE`** | A field written by a player choice is never read by any rule on any reachable path. | Sylvester [S19]; Short "decorative" [S34] | Static: the field has no reader in rules. Dynamic: written and never read across all persona runs. | 3 | S+M | Low statically. Dynamically, coverage-limited. |
| **C-2 `REWARD_WITHOUT_CAUSE`** | The player gains an advantage, item, or praise that no player decision caused. | SDT competence needs contingency [S6]; Nelson "not to depend much on luck" [S14] | State delta favorable to the player, with no player input frame in its causal read chain (e.g., random loot, a narrator claiming credit). | 3 | M+J | Medium. Seeded luck is legitimate if it is rare and framed as luck. |
| **C-3 `HOLLOW_CONSEQUENCE`** | A choice has a real, perceivable effect, but its value is negligible relative to what it cost or promised. | Meier trade-offs [S5]; Kennedy resource scarcity [S40] | Shortest-path or outcome-distribution delta between the with-choice and without-choice replays is below a threshold (e.g., saves ≤1 move; changes win probability by <5% over N seeded combats). **Current example: the Mira shortcut [obs].** | 4 | M | Medium. Some payoffs are emotional, not mechanical. The judge may certify an emotional payoff by quote. |
| **C-4 `DEAD_WEIGHT_ITEM`** | A takeable object is never consumed, shown to anyone, or read by any rule. | PLAY_DESIGN Hypothesis B; Nelson red herrings [S14] | Static item-reader audit. Dynamic: carried at session end with zero reads. **Current: 4 objects [obs].** | 2 | S | Low. Deliberate red herrings must be declared, and there should be few. |
| `PERSISTENCE_BREAK` (existing) | A recorded change is absent after leaving and returning. | PLAY_DESIGN persistence | Snapshot diff on re-entry. | 5 | M | Very low. |
| `DIALOGUE_CALLBACK_BREAK` (existing) | An established memory fact isn't reflected on its documented callback path. | Short salience [S39] | Memory flag set, callback path taken, expected line absent. | 4 | M | Low. |

#### Family K: Curiosity (P2)

| Mode | Definition | Theory | Observable signature | Sev | Detect | FP risk |
|---|---|---|---|---|---|---|
| **K-1 `OPEN_LOOP_ABANDONED`** | Text marks something as anomalous (missing, broken, wrong, silent, sealed, locked, "no obvious...") and no rule ever pays it off. | Loewenstein gap [S2]; Nelson red herrings / "understand a problem once it is solved" [S14]; Three Clue Rule [S9] | Static: an anomaly-lexicon hit in the description of object O, with no rule that reads O or its referent, and no registered payoff ID. **Current: clapperless bell, stone compass [obs].** | 4 | S+J | Medium. Pure atmosphere can use anomaly words. Each such use must be registered as `atmosphere_only`, and the register is itself reviewed. |
| **K-2 `GAP_TOO_WIDE`** | A question is opened, but the player lacks enough clues to form any hypothesis. | Inverted-U curiosity [S2, S3]; Three Clue Rule | Payoff requires a fact with fewer than 2 distinct clue sources reachable before it; player journals or think-aloud show random guessing. | 3 | S+H | Medium. |
| **K-3 `GAP_TOO_NARROW` / `SPOILED_REVEAL`** | The answer is stated before the player could wonder, or the reveal restates what the player already knew. | Inverted-U [S3]; Schell surprise [S7] | The payoff fact appears in output before or together with the first clue. The judge quotes both. | 2 | M+J | Medium. |
| **K-4 `RETCONNED_TRUTH`** | A hidden fact changes after it has been hinted at. | PLAY_DESIGN "hidden truth"; RPGBench [S31] | The hidden-fact field value differs between the clue turn and the reveal turn. | 5 | M | Very low with Python-owned facts. It would indicate a severe bug or LLM authority leak. |
| `FALSE_AFFORDANCE` (existing) | A cue invites an action the interface can only generically refuse. | Nelson "a good reason why something is impossible" [S14] | Judge quotes the cue and the refusal. | 3 | J | Medium. Players try things for fun. Require the cue to be salient (named object, in the most recent `look`). |

#### Family L: Legibility and momentum (P3)

| Mode | Definition | Theory | Observable signature | Sev | Detect | FP risk |
|---|---|---|---|---|---|---|
| `UNRECOGNIZED_COMMAND` (existing, re-scoped) | An off-convention command gets the generic unrecognized response. | Nelson verbs/synonyms [S14] | Known "unrecognized" response string. | 2 | M | Low. |
| **L-2 `CONVENTION_CLASH`** | An input that follows a near-universal genre convention is refused or misread. | Nelson rights 8–10 [S14]; PXI "ease of control" [S43] | The input is in a fixed convention lexicon (`n/s/e/w`, `north`, `go X`, `x`/`examine`, `i`/`inventory`, `get`) and the response is unrecognized or a different action. **Current: `north`, and `s`=status [obs].** | 4 | M | Low. |
| **L-3 `TUTORIAL_CLIFF`** | A cluster of failed inputs at the start of the session. | GameFlow clear goals and feedback [S8]; RITE's focus on tutorials [S45] | ≥3 refused or unrecognized inputs among the first 10 frames, or a first meaningful state change later than frame 8. | 4 | M | Medium. Deliberate exploration of the interface looks similar, so read it together with the journal. |
| **L-4 `MENU_WALL`** | The interface frames play as a fixed verb menu, and players stop attempting anything off-menu. | OSR "rulings not rules" [S10]; SDT autonomy [S6] | Off-menu attempt rate falls to 0 after the first refusals, and the action-type entropy of the whole session is below a threshold. Look for the journal saying "I guess I can only...". | 3 | M+J | High. A focused player may just be efficient. Pair it with journal evidence of an unsupported intent. |
| **L-5 `LATENCY_BREAK`** | Wall-clock delay between input and the first byte of the response exceeds budget. | Flow immediate feedback [S4, S8]; Doom [S24] | Timestamp delta > 1.5 s (soft) or > 5 s (hard), per frame. The count per session is the metric. | 3 (hard) | M | None. It is a pure measurement. |
| **L-6 `INPUT_TAX`** | Keystrokes or prompts per meaningful action are above budget. | Nelson "not to do boring things" [S14] | Frames per state-changing action > 1.5 on average. **Current: `move` → `Direction:` is two frames per move [obs].** | 2 | M | Low. |
| **L-7 `NAVIGATION_LOSS`** | The player loses the map. | Romero landmarks and flow [S23] | Journal asks where something is, or three or more back-and-forth moves happen without a new room or state change. | 2 | M+J | Medium. |
| `PACING_DRAG` (existing) | Low-information turns that could be removed without losing any decision. | PLAY_DESIGN pacing | Judge-quoted. Add a mechanical proxy: ratio of output words to new-fact atoms. | 2 | J+M | Medium. |
| `REPEATED_RESPONSE` (existing) | The same normalized response three times without a state change. | Compton oatmeal [S33] | As planned. | 3 | M | Low. |

#### Family D: Decisions and stakes (P4)

| Mode | Definition | Theory | Observable signature | Sev | Detect | FP risk |
|---|---|---|---|---|---|---|
| **D-1 `DOMINANT_ACTION`** | One option is correct in nearly every situation where it's available. | Meier "always choose the first" [S5] | In combat frames, the modal action share is ≥90% across personas and seeds, and a simulated always-modal policy has win rate ≥ the best persona's. **Current: `attack` [obs].** | 4 | M | Low. The simulation makes it robust. |
| **D-2 `CHOICE_ILLUSION`** | Options presented as meaningfully different converge on the same possibilities. | Ashwell bottlenecks [S15]; SDT autonomy [S6] | Two options share a verb set and differ only in numeric parameters. Outcome-projection distributions overlap beyond a threshold across seeded runs. **Current: class choice [obs].** | 3 | S+M | Medium. Stat-only differences can matter to tacticians, so check outcome spread. |
| **D-3 `STAKES_OPACITY`** | The player commits to a risk without being able to see its size beforehand. | Into the Breach telegraphing [S27]; Blades visible clocks [S11]; Nelson "killed without warning" [S14] | An encounter starts or a hazard triggers, and no prior output described its threat level or offered an alternative. **Current: entering a room with an enemy forces combat, with no retreat [obs].** | 4 | M+J | Medium. Surprise ambushes are legitimate if rare and signalled somewhere. |
| **D-4 `COSTLESS_OPTIMUM`** | The thorough path is strictly better, so choosing becomes "do everything". | Meier trade-offs [S5]; Terra's own "honest limit" (terra_plan2) | The full-exploration persona beats the others on every outcome metric at no measured cost (time, HP, clock). | 3 | M | Low. |

#### Family F: Failure (P5)

| Mode | Definition | Theory | Observable signature | Sev | Detect | FP risk |
|---|---|---|---|---|---|---|
| **F-1 `FAIL_WITH_NOTHING`** | A failure produces no state change, no new information, no new option, and no carryover. | PbtA moves [S13]; PLAY_DESIGN "meaningful failure" | Failed check, miss, or refusal followed by an unchanged outcome projection and no new fact atom. Death that writes nothing to any persistent record. | 4 | M | Medium. Combat misses are allowed to be cheap. Scope the mode to non-combat attempts plus death. |
| **F-2 `FAIL_FORWARD_FAKE`** | A "failure" delivers the intended success by another route. | Fail-forward critiques [S29] | Failed check, and within 2 frames the same goal state is reached without any new player input. | 3 | M | Medium. |
| **F-3 `UNSIGNALED_DEAD_END`** (existing; mapped to Zarf "Nasty/Cruel" [S22]) | No progression path remains, and nothing says so. | Zarf [S22]; Nelson [S14] | As planned. | 5 | M | Low. |
| `COMBAT_SOFTLOCK` (existing) | Combat cannot advance. | – | As planned. | 5 | M | Very low. |

#### Family V: Voice and LLM integrity (P6)

| Mode | Definition | Theory | Observable signature | Sev | Detect | FP risk |
|---|---|---|---|---|---|---|
| `WORLD_STATE_CONTRADICTION` (existing, widened) | Any rendered text contradicts the snapshot. | RPGBench [S31] | Fact-to-text rules over *all* output: static descriptions, `look`, bank, `DM:`. **Current: "sealed vault" [obs].** | 5 | M | Low for rule-covered facts. |
| **V-1 `NARRATOR_INVENTION`** | A `DM:` line introduces an entity, number, exit, item, or capability absent from its fact packet. | Short decorative [S34]; project SYSTEM_PROMPT | Noun phrases or numbers in the `DM:` text that don't match the fact-packet vocabulary, the room object names, or an allowed atmosphere lexicon. The judge confirms by quote. | 4 | M+J | Medium. Metaphor ("teeth of the dark") can trip it, so use the allowlisted lexicon. |
| **V-2 `SYCOPHANTIC_SPIN`** | Narration misrepresents a bad outcome as good, or praises the player independent of outcome. | Sharma sycophancy [S35] | `hit=false` or `damage_to_hero>0` events whose `DM:` line has positive-valence praise terms ("deftly", "masterfully", "heroically") about the player. | 3 | M+J | Medium. |
| **V-3 `NARRATOR_AMNESIA`** | Narration ignores or contradicts a fact present in its packet or in an earlier `DM:` line. | Lost in the Middle [S36]; FIREBALL [S37] | The fact is in the packet (e.g., `mira_remembered_prior_ask=true`), and the `DM:` line contradicts it, or treats a known NPC as a stranger. | 4 | M+J | Medium. |
| **V-4 `RAILROAD_VOICE`** | Narration tells the player what to do, feel, or decide. | DW "address the characters", "never speak the name of your move" [S13]; SDT autonomy [S6] | Imperatives aimed at the player ("You must...", "You should head north") or asserted emotions ("You feel certain...") in `DM:` lines. | 2 | M | Medium. Diegetic NPC advice is fine. |
| **V-5 `OATMEAL`** | Generated texture is perceptually undifferentiated. | Compton [S33]; Short [S34] | Mean pairwise similarity (character 4-gram Jaccard, or embeddings) across a session's `DM:` lines is above threshold; stock-phrase frequency is high ("ancient", "whispers", "air thick with"). | 2 | M | Low as a measurement. The threshold needs human calibration. |
| **V-6 `META_LEAK`** | Output exposes the machinery: JSON, "as an AI", rules text, prompt fragments. | Mimesis, as in Nelson's essay [S14] | Regex over `DM:` lines. | 3 | M | Low. |

#### Family I: Identity (P7)

| Mode | Definition | Theory | Observable signature | Sev | Detect | FP risk |
|---|---|---|---|---|---|---|
| **I-1 `ANONYMOUS_PROTAGONIST`** | Nothing in the world reflects who this player has been (their choices, class, history) after the first third of the session. | SDT relatedness [S6]; Hades reactivity [S41] | No output after frame N/3 that is conditioned on a player-history field. | 2 | M | Medium. |
| **I-2 `NPC_WITHOUT_STAKE`** | An NPC has no goal the player can affect. | PLAY_DESIGN NPC memory; DW "give every monster life" [S13] | The NPC has no state field that player actions can write. | 2 | S | Low. |

**Human-only modes.** No script can see these; record them with `source: human` (section 6):
- `BOREDOM` (visible disengagement, phone checks)
- `CONFUSION_SILENT` (long pause without trying anything)
- `DISCOMFORT` (content that lands badly with a particular student)
- `SOCIAL_FLAT` (in pairs, the partner stops contributing)

---

## 4. Positive-signal taxonomy

Failure counts alone reward deleting content, which Terra already guards against. The positive signals give evidence that the loop is working. Each signal below is **behavioral first**: an action in the canonical transcript. The journal or think-aloud only *corroborates*.

| Signal | Evidence rule (transcript-first) | Theory | Gaming risk and guard |
|---|---|---|---|
| `DISCOVERY` (existing) | First encounter of a room, object, or fact atom. | Loewenstein [S2]; MDA "Discovery" [S1] | Adding rooms or objects inflates it. Normalize per reachable content unit and pair with K-1/C-4 (discoveries that go nowhere don't count as positive). |
| `EARNED_CONSEQUENCE` (existing) | A player-written field is later read by a rule and the read is rendered. | P1 | Adding trivial reads inflates it. Count only reads that change an outcome projection (not C-3 hollow). |
| `CALLBACK` (existing) | Output conditioned on earlier player history. | Short salience [S39] | Barks that mention history without mechanics inflate it. Split into `CALLBACK_TEXT` and `CALLBACK_MECHANICAL`; report both. |
| `RETURN_INTENT` (existing) | The player deliberately revisits a place or NPC, citing an earlier turn. | Romero revisits [S23]; Hypothesis A | Model players told to "explore" revisit mechanically. Require the revisit to precede a state-changing action there. |
| **`HYPOTHESIS`** | The player states a guess about hidden truth (journal or think-aloud), *and* the next ≤3 frames contain an action that tests it. | Loewenstein gap [S2]; OSR player skill [S10] | Verbose model players narrate endless guesses. Only count guesses followed by a testing action, at most one per gap. |
| **`DELIBERATE_CARRY`** | A takeable item with no current use is taken, and a later frame attempts to use or show it. | Hypothesis B | Hoarder personas take everything. Require the later *attempt*, not just the take. |
| **`PLAN`** | A multi-step intention referencing ≥2 state facts, followed by execution of ≥2 of its steps. | Meier long-term decisions [S5] | The golem prompt must not mention plans. Count execution, not the statement. |
| **`INFORMED_RISK`** | The player takes a risky action after output that described the risk, with a stated reason. | Into the Breach [S27]; Blades [S11] | Only possible if the game signals risk. That's intended: D-3 and this signal move together. |
| **`RECOVERY`** | After a failure (F-family event or HP loss >30%), the player changes approach rather than repeating or quitting. | SDT competence [S6]; PbtA [S13] | Check that the action type differs from the failed one. |
| **`OFF_MENU_ATTEMPT`** | A plausible action outside the current verb set. | OSR [S10] | *Dual-use:* this is positive (agency desire) *and* raw material for `UNSUPPORTED_INTENT`. Report both; the ratio of attempts to refusals is the story. |
| **`FREE_CHOICE_CONTINUE`** | The player keeps playing after the nominal goal, or after being told they may stop. | Deci free-choice paradigm; IMI documentation [S42] | Humans only (see section 6). A model player has no free choice. Never compute it for golems. |
| **`FIRST_PERSON_RETELLING`** | In the debrief, the player retells an event as "I did X, so Y". | Ryan curation [S21]; PLAY_DESIGN "story is what the player remembers" | Humans only. Code it from the debrief transcript. Count causal connectives tied to real transcript events. |
| **`SURPRISE_WITH_SENSE`** | Expressed surprise, followed by an explanation that matches the actual cause. | Schell surprise [S7]; PLAY_DESIGN §8 | The judge must quote the surprise and the causal state. |

**Anti-gaming rules, general [synth]:**
1. No positive signal counts unless it is anchored to a canonical transcript turn and a snapshot field.
2. Golem prompts never contain the signal names or their descriptions (a model shown "HYPOTHESIS" will manufacture hypotheses).
3. Report positive signals *per reachable content unit*, never as raw totals.
4. Any positive signal whose count moves more than 2× between builds with no corresponding design change triggers an audit.
5. Signals and failures are never netted into a single score.

---

## 5. Measurement guidance

### What a model-player transcript can tell you

- **Mechanical truth:** persistence, contradictions, softlocks, dead ends, dead state, dominant actions, latency, input tax. These are *facts about the build* that don't depend on who plays. Model players are excellent **fuzzers with a theory of mind**: they generate plausible, varied inputs faster and more systematically than humans.
- **Legibility, as proxy evidence:** if a patient, literate model player misses a causal bridge, a student almost certainly will. The converse doesn't hold.
- **Affordance coverage:** what a genre-literate player *tries*. Model players have read a lot of D&D and IF, so they try `cast fireball`, `x bell`, and `ring bell`, which is useful for the unsupported-intent ledger.

### What it cannot tell you

- **Feelings:** boredom, delight, suspense, attachment, or whether novelty wears off on the second play.
- **Representative behavior:** LLM players are unusually patient, literal, verbose, and compliant, and RLHF assistants lean toward agreeable output [S35]. A golem's "I'm curious to see..." is a stylistic default, not a measurement.
- **Free choice:** a model player continues because it was told to. `continue: 0|1` in golem journals is at best a proxy for "an interruption point was reached". It must never be reported as engagement.
- **Social play, accessibility, cultural fit, and difficulty for novices.** A model is never a novice at text.

### Goodhart guards beyond those already planned

Manheim & Garrabrant distinguish regressional, extremal, causal, and adversarial Goodhart [S44]. Each maps onto a concrete hazard here:

| Variant | How it would bite this project | Guard |
|---|---|---|
| Regressional (the proxy is noisy) | Judge FP/FN noise makes a 12→9 change look like progress. | Report confidence intervals (below). Never declare a change on fewer than ~3 paired seeds per persona. |
| Extremal (the proxy fails out of distribution) | Deleting descriptive nouns eliminates `FALSE_AFFORDANCE` *and* curiosity. | Coverage floors (planned). Also **K-1 and C-4 static audits**: a build that removes the bell *and* its gap looks better on FALSE_AFFORDANCE but not on DISCOVERY per unit. Track a "gaps opened and closed" count and require it to stay at or above baseline. |
| Causal (intervening on the proxy doesn't move the goal) | Adding "Mira remembers you" barks raises `CALLBACK` without any mechanical memory. | Split `CALLBACK_TEXT` from `CALLBACK_MECHANICAL`. Use the **counterfactual ablation twin**: every claimed consequence must survive a replay with the decision flipped, and differ in its outcome projection. |
| Adversarial (optimizers game the metric) | Builder agents (Brenda) that can read detector code will satisfy detectors, not players. | Builders never get detector source or holdout fixtures. Rotate detector thresholds privately. The judge model family must differ from both builder and narrator families (Zheng et al. document self-enhancement bias [S46]). |

**Additional guards [synth]:**
- **Human spot audits:** 10% of accepted judge instances *and* 10% of discarded ones go to a human every baseline cycle.
- **Detector retirement:** when a mode stays at zero for three baselines, its fixture keeps running but the mode leaves the headline report. That stops "zero verified X" from padding reports.
- **Build-blind judge:** the judge never sees the build SHA, the version, or which side of a comparison a transcript came from. Randomize pair order to counter position bias [S46].
- **Fixed content-unit denominators,** declared per build in the manifest.

### Calibrating the LLM judge against humans

1. **Gold set.** Jeremy plus one or two trained raters independently label about 150 candidate instances drawn from real transcripts. Stratify to at least 10 per judge-eligible mode, and include ~30% true negatives.
2. **Human–human agreement first.** Compute Cohen's κ (two raters) or Krippendorff's α (more) per mode. If humans can't agree on a mode (say α < 0.6, a common convention, not a law), **the mode's definition is the problem**; rewrite it before training any judge on it.
3. **Judge–consensus agreement per mode:** precision, recall, and κ against the human majority. Zheng et al. report GPT-4-class judges reaching over 80% agreement with humans on chat preferences, "the same level of agreement between humans" [S46]. That was a different task. Don't assume it transfers; measure it.
4. **Gate:** a mode is judge-eligible only when judge precision ≥ human–human pairwise precision minus a small margin. Otherwise it stays human-only.
5. **Recalibrate** whenever the judge model, its prompt, or the taxonomy text changes, because each counts as a new instrument.
6. **Bias probes:** duplicate a transcript with padded prose (verbosity), swap order (position), and have the narrator model judge itself (self-enhancement) [S46]. Report the deltas.

### Sample sizes and effect sizes, stated honestly

- **Rates from golem runs.** The baseline is 6 personas × ≤35 frames ≈ 210 frames. With Poisson counts, 10 observed instances gives an exact 95% interval of roughly 4.8–18.4 instances. A later build showing 7 is *indistinguishable*. Treat per-mode rates from one baseline as **problem discovery, not measurement**. Trend claims need multiple seeds per persona (paired) and preferably a sign test across pairs: "improved on 9 of 10 seed pairs" beats a pooled rate.
- **Problem discovery with humans.** Nielsen's model gives the chance of seeing a problem as 1 − (1 − p)ⁿ, with an average per-user discovery rate of about 31% across his projects, hence "5 users find ~85%" [S47]. The average hides the tail. A problem that affects 10% of players is seen by 5 players only 41% of the time, by 15 players 79%, by 29 players 95% (arithmetic from the same formula). Faulkner's resampling study reportedly found random 5-user sets finding anywhere from 55% to 99% of problems [S48]; I saw those numbers only in secondary summaries. Nielsen himself recommends several small iterative rounds and about 20 users for quantitative studies [S47].
- **The "want to continue" proportion.** With 20 students, a 95% interval on an observed 50% is about ±22 points. Comparing two builds between-subjects at that size only detects enormous differences (roughly 30% versus 75%). Within-subject designs (each student plays two builds) are more powerful, but order and learning effects confound them. Counterbalance, and accept that the second play is contaminated by knowing the map.
- **Single-item instruments are noisy.** The miniPXI's single items had reliability estimates of .51–.83, and validity was confirmed for 9 of 11 constructs [S43b]. With classroom n, report per-item distributions and quotes, not significance tests.
- **The honest bottom line:** with this project's resources, humans are for **finding** problems and **validating** direction. Golems are for **regression testing** known problems. Neither gives publishable effect sizes without a much larger study.

### What must be measured by humans

- `FREE_CHOICE_CONTINUE` (the north-star behavioral measure)
- `FIRST_PERSON_RETELLING`
- Boredom and confusion in their silent forms
- Emotional valence
- The tutorial experience for a real novice
- Whether `DM:` text is read or skipped (watch the eyes, or ask)
- Whether a surprise "made sense"
- Accessibility (screen readers, color, reading load)
- Whether anything is uncomfortable for a student

---

## 6. Human playtest protocol

The goal is to run sessions that produce ledger-compatible evidence without turning students into lab rats.

### 6.1 Jeremy solo sessions (design evidence)

Jeremy is invested and already knows the design, so his sessions can't measure first-contact curiosity. They are best at spotting legibility and consequence failures, and at seeing whether the *second* play holds up. Protocol:

1. **Setup (2 min).** The harness records the canonical transcript: seed, build SHA, timestamps. Jeremy uses a pseudonymous hero name.
2. **Play (20–25 min), concurrent think-aloud** in a light form: speak when surprised, confused, or deciding. A voice memo or a second person typing notes with timestamps. Concurrent think-aloud can change task behavior (reactivity) [S49]. That is acceptable for design discovery and unacceptable for timing data, so latency comes from the harness, not from think-aloud sessions.
3. **Stop and free choice.** At a natural break, Jeremy asks himself the PLAY_DESIGN question honestly and records whether he wants to continue *before* answering anything else.
4. **Retrospective (10 min).** Walk back through the transcript. At every `DM:` line, note whether he read it. At every refusal, note what he meant. That is retrospective think-aloud cued by the log, which trades reactivity for memory loss [S49].
5. **Ledger.** Code each observation into a mode or signal (6.4).

### 6.2 Classroom sessions (first-contact evidence)

**Format.** Solo play on laptops works best, with one facilitator per 4–6 students who observes and takes timestamped notes. As an alternative, *pairs* (driver and navigator) talk naturally, which gives think-aloud without prompting. Pair conversation (constructive interaction) is an established usability alternative to solo think-aloud [S50]. It changes the experience, though, and pair data shouldn't be pooled with solo data.

**Run in RITE rounds, not one big study.** Medlock et al.'s RITE method fixes problems after as few as one participant and keeps testing until the next participants surface no major issues. In their Age of Empires II tutorial case, 10 participants led to changes and the next 6 needed none [S45]. A class of 24 can run as three or four rounds of 6, with an Ivy fix cycle between rounds for *mechanical* problems only. Content redesign waits.

**Session structure (≈35 min):**

| Time | Activity |
|---|---|
| 0–3 | Consent script (6.5). Pseudonym assignment. One sentence of framing: "This is an unfinished game. We are testing the game, not you. There are no wrong moves." Don't explain commands. The tutorial is part of what's being tested. |
| 3–25 | Play. The facilitator notes time-stamped *behaviors*: first meaningful action, stuck moments longer than 30 s, visible reactions, things said aloud. The facilitator answers no game questions. If asked, they say "what would you try?" and log it as a `TUTORIAL_CLIFF` candidate. |
| 25 | **Free-choice moment:** "That's all the time we need for the test. You're welcome to stop, or keep playing while I get the next part ready — completely up to you." Then the facilitator visibly disengages for 5 minutes. |
| 25–30 | Record `FREE_CHOICE_CONTINUE`: did they continue (yes/no), how many frames, and whether they stopped on their own. |
| 30–35 | Post-play instrument (6.3), then two open questions. |

**Why the free-choice design?** Free-choice behavior after the required task ends is the classic behavioral index of intrinsic motivation in SDT research. The IMI's own documentation warns that when people are ego-involved they show "pressured persistence" that doesn't track interest [S42]. So: no grading, no leaderboard, no "see if you can beat it". Ask for no self-report before the free-choice window.

### 6.3 The short post-play instrument (≈3 min)

This is built from validated sources and **paraphrased, not reproduced**. Use the original items from the cited papers in real use, subject to their terms. The PXI and miniPXI are published in academic venues. The IMI is free for academic use [S42]. PENS is reportedly licensed commercially through Immersyve; I couldn't verify its terms, so it is omitted.

- **Seven-point agree/disagree items (−3 to +3), one per construct, following the miniPXI single-item approach [S43, S43b].** Paraphrased targets:
  1. *Curiosity:* the game made me want to find things out.
  2. *Autonomy:* I felt free to play the way I wanted.
  3. *Mastery:* I felt capable while playing.
  4. *Meaning:* playing felt like it mattered to me.
  5. *Goals and rules:* I understood what I was trying to do and how.
  6. *Progress feedback:* I could tell how well I was doing.
  7. *Ease of control:* the commands were easy to use.
  8. *Enjoyment:* I liked it.
- **Two items from IMI Interest/Enjoyment [S42]**, paraphrased, for convergence with item 8: "I'd describe this as very interesting"; "I thought this was boring" (reverse-scored).
- **Three open questions [synth],** each mapped to a principle:
  - "What is one thing you wanted to find out but never did?" (P2: finds K-1 and K-2 gaps, and doubles as curiosity evidence)
  - "Describe one moment where something happened *because of* what you did." (P1; also yields `FIRST_PERSON_RETELLING`)
  - "Where did the game not understand you, or where did you get stuck?" (L-family)

Caveats: the GEQ is widely used, but its seven-factor structure wasn't supported in a large validation (N=633), and its citation history is messy [S51]. Don't use it as the primary instrument. The PXI has an independent large-sample validation [S52]; I only skimmed its abstract.

### 6.4 Converting human findings into the same ledger

Every human observation becomes a ledger record with the same schema as detector and judge instances, plus provenance:

```json
{"mode":"TUTORIAL_CLIFF","source":"human","rater":"facilitator_B",
 "session":"<harness run id>","turn_ids":[1,2,3],
 "quote":"<exact transcript substring OR verbatim think-aloud note>",
 "quote_origin":"transcript|observer_note|debrief",
 "severity_observed":"session_ending|recovered|minor"}
```

Rules:
- A human instance whose quote comes from the transcript passes the same quote gate as the judge.
- Observer-note quotes are accepted but flagged `unverifiable_by_script`.
- Human-only modes and signals (`BOREDOM`, `FREE_CHOICE_CONTINUE`, `FIRST_PERSON_RETELLING`) carry `source: human` only.
- Human instances on judge-eligible modes feed the calibration gold set (section 5).
- Report human and machine counts **side by side, never summed.**

### 6.5 Consent and privacy basics for students

This is not legal advice. The institution's IRB and FERPA office decide.

- **Classroom improvement versus research.** US federal exemption category (d)(1) covers "research conducted in established or commonly accepted educational settings that specifically involves normal educational practices" not likely to hurt students' opportunity to learn [S53]. **The IRB, not the instructor, decides whether exemption applies.** If results might ever be published or presented as research, get the determination *before* the session.
- **Power dynamics.** Jeremy grades these students, so participation must be voluntary, ungraded, with an equivalent non-play activity for anyone who opts out. Where feasible, a TA runs the session and Jeremy sees only de-identified data.
- **Data minimization.** The game's session recorder logs the **hero name** (`session_started`, `character_created`) [obs]. Instruct students to use an assigned pseudonym, not their real name. Store transcripts under random IDs. Don't audio-record by default; use written observer notes. Follow the foreman policy "harvest, use, delete" (`docs/STUDENT_DATA_RETENTION.md`): keep only de-identified derived ledger records, and delete raw transcripts once coded.
- **Free text is an identification risk.** Students may type their own names or personal content into free-text commands, especially if an intent interpreter is added later. Scrub before any model-judge pass. Never send student transcripts to a third-party API without explicit consent and a data review.

---

## 7. Creative directions

These are ten directions, ranked, with the top two recommended for building first. Each keeps the rule: **Python decides, the LLM describes.** "Pre-bake" means authored offline by frontier models, validated by Python, and shipped as data. "Live" means generated at play time by the local model (8 GB GPU or 24 GB Mac).

### D-1. Doom for D&D: "The Fast Delve" (Rank 1, build first)

**The fantasy.** "I am a fast, dangerous, clever delver. Every room is a crisp tactical problem I can read at a glance and solve in six keystrokes. When I play boldly, the dungeon feeds me."

**Doom's essence, translated [synth], sources [S23–S25, S27]:**

| Doom property | In the Delve |
|---|---|
| Instant response | Every input resolves in <100 ms. No live LLM in the hot loop. Banked texture only. |
| Tactile feedback | Each hit or miss has a distinct, state-bearing line: "your blade skids off the captain's pauldron (AC 16 vs 14)". Precomputed variant tables are keyed on (verb, outcome, margin, enemy-state), so no two consecutive lines repeat. |
| Readable level design | Room zones (near / far / high ground / doorway). Landmarks named in every exit line ("east, toward the dripping bell"). A visible-but-unreachable place in the first three rooms that is reachable later (Romero's "if a player could see outside..."). One secret per 3–4 rooms. |
| Push-forward combat | No resting for HP. Enemies drop what you need (potion shards, a thrown weapon) when defeated *with a tactic* (shoved into a hazard, disarmed, finished at low HP). Turtling costs a clock tick. |
| Telegraphed enemy intent | Before your turn: "The captain rears back for a cleaving blow at the doorway." Into the Breach-style legibility turns combat into a decision (D-1 `DOMINANT_ACTION` dies). |
| Verbs, not menus | Single-key verbs: `a`ttack, `s`hove, `b`race, `t`hrow, `u`se, and direction keys. Directions work at the top prompt. |
| Moddability (WADs) | Rooms, enemies, intents, hazards and texture as validated JSON/TOML "delve packs". Students author a room as a class exercise, and the validator is the gate. |

- **Engine needs:** a zone model per room; enemy intent tables; a small action economy (shove/brace/throw); a hazard object type; a data-pack loader and validator; a latency and input-tax meter in the harness.
- **Authority split:** fully Python. The LLM is absent from combat. Offline authoring produces variant tables, validated by the terra_plan2 bank validator extended to allow state-keyed facts.
- **Biggest risk:** it becomes a tactics puzzle and loses D&D's "try anything". Mitigation: hazards and objects are the tactic surface, so the player uses the world, not just their stats.
- **Moves:** L-4, L-5, L-6, D-1, D-3, F-1 (↓); `PLAN`, `INFORMED_RISK`, `RECOVERY` (↑).

### D-2. The Seeded Mystery on a storylet spine (Rank 2, build second)

**The fantasy.** "Something happened here, and each run it is *different*. I am piecing it together, and when I figure it out, the ending changes because I did."

**Design.**
- At seed time, Python commits a hidden truth from a small authored space: who killed the keeper, why the bell lost its clapper, the captain's weakness, which of three routes is trapped.
- Following the Three Clue Rule [S9], Python places at least three clue storylets for every fact the payoff needs, spread across rooms, NPC lines, and objects.
- The payoff is a player *act*, not a quiz: showing Mira the right object, ringing the bell with the right clapper, choosing where to fight the captain. Python resolves it and the final encounter changes.
- The bell and compass become gaps that close (K-1 fixed by design), and the star chart becomes one clue among several (terra_plan2 generalised).

**The storylet spine.** Clues and reactions are storylets (Short QBN/salience [S39]): preconditions over Python qualities, a salience score, effects validated by Python, and text variants. Following Kennedy [S40], *story facts* are kept separate from *spendable resources*.

**Engine needs:** a hidden-fact table per seed; a storylet runtime (select the highest-salience eligible storylet; apply validated effects); a clue-coverage validator ("every payoff fact has ≥3 reachable clues on every seed") that runs in CI as a static test.

**Pre-bake versus live.** A frontier model authors a few hundred clue storylets offline, per fact value, per location, in 2–3 phrasings each. Python validates them for fact closure (text may mention only the atoms the storylet declares), reachability, and vocabulary. The live model runs only when the player does something off-graph with a clue object, and even then it may only select among validated storylets or phrase a declared fact.

**Biggest risk:** clue legibility. Students miss clues (K-2), or guess-spam the payoff. Mitigate with proactive clues [S9] triggered by a clock ("the captain's patrol finds the keeper's journal first").

**Moves:** K-1, K-2, K-4, C-1, C-4, D-2 (↓); `HYPOTHESIS`, `DELIBERATE_CARRY`, `SURPRISE_WITH_SENSE`, `FIRST_PERSON_RETELLING` (↑).

### D-3. Visible clocks and a living delve (Rank 3, a cheap companion to D-1 and D-2)

- **The fantasy:** "The dungeon is moving while I am in it."
- **Mechanics:** Blades-style visible clocks [S11]. "Captain's patrol" (ticks on noise, fleeing, and every N moves); "Cistern flooding" (opens and closes routes); "Mira's patience". Clocks are Python state, shown in `status` and in room headers, and describe the obstacle, not the method [S11]. Soft moves become hard moves when ignored (Dungeon World [S13]). "Think offscreen too": the patrol moves between rooms deterministically.
- **Why it matters:** it gives *time* a cost, which turns terra_plan2's chart detour into a real trade-off (D-4 `COSTLESS_OPTIMUM` fixed), and gives failure somewhere to go (F-1).
- **Risk:** anxiety for novices. Tune the first clock to be slow and visible.
- **Moves:** D-4, F-1, D-3.

### D-4. The Delve Remembers: roguelike legacy (Rank 4)

- **The fantasy:** "My last hero died here. This hero finds her sword, and Mira remembers her."
- **Design:** permadeath per run (Berlin Interpretation [S28]), plus a *legacy file* of Python meta-state that survives death: corpses and gear left in place, NPC attitudes toward "those who came before", lore facts learned, and one-line graffiti the player may leave from a closed phrase grammar. Legacy-conditioned storylets are pre-baked.
- **Risk:** grind and save-scumming. Also, a persistent file on shared lab machines is a student-data question (6.5).
- **Moves:** F-1, I-1 (↓); `RETURN_INTENT`, `RECOVERY`, `FREE_CHOICE_CONTINUE` (↑).

### D-5. The Chronicle: retrieval-grounded world memory and saga (Rank 5)

- **The fantasy:** "At the end, the game tells *my* story back to me, and it is true."
- **Design:**
  - Every Python event goes to an append-only event log with IDs. It already nearly exists in `SessionRecorder`.
  - A retrieval layer selects fact atoms for NPC dialogue by recency, importance, and relevance, the scoring Park et al. use for generative agents [S54]. The NPC then never needs a transcript and avoids lost-in-the-middle amnesia [S36].
  - At session end, a *chronicle* is generated (Caves of Qud-style biography generation from event sequences [S55]; Ryan's curation [S21]). Every sentence must cite event IDs, and the quote-gate idea is reused to reject any sentence whose cited events don't support it.
  - The chronicle runs after play, so it can use the 24 GB Mac model or a frontier model offline, with no latency cost.
- **Risk:** small-model hallucination in the saga. The citation gate is the guard. There is also privacy if the saga includes student free text.
- **Moves:** V-1, V-3 (↓); `FIRST_PERSON_RETELLING`, attachment (↑). It is also a strong classroom artifact: students compare sagas.

### D-6. The Intent Interpreter as PbtA moves (Rank 6)

- **The fantasy:** "I can type anything, and the world answers fairly."
- **Design:** free text → the local LLM classifies it into a *closed* move set (Defy Danger, Discern Realities, Parley, Use X on Y, Force, Sneak) with structured arguments, using schema-constrained decoding (Ollama structured outputs [S56]). Python validates the arguments against the world, rolls in tiers (10+ / 7–9 / 6−, following Dungeon World [S13]), and on 7–9 or a miss picks a GM move from a Python table. The LLM never picks the outcome tier. Unclassifiable input gets an in-fiction clarifying question, never a generic refusal.
- **Risk:** misclassification feels worse than a menu; 2–10 s latency per free-text action; a huge `UNSUPPORTED_INTENT` surface. It needs a formal plan because it moves the authority boundary *closer* to the LLM.
- **Moves:** L-4, `UNSUPPORTED_INTENT`, `FALSE_AFFORDANCE` (↓); `OFF_MENU_ATTEMPT` (↑, and resolved).

### D-7. The Shared Delve: asynchronous class world (Rank 7)

- **The fantasy:** "Others were here, and the world remembers *us*."
- **Design:** one persistent delve per class, played solo but asynchronously. Each student's run leaves Python-validated traces for others: template messages in the Dark Souls mold, from a closed grammar ("Try ___ ahead"); corpses; NPC attitudes aggregated across players. This fits Jeremy's standing rule that student work is a shared learning resource (`AGENTS.md`).
- **Needs:** a server, per-class state, moderation of the template grammar, and privacy review.
- **Risk:** infrastructure, abuse, and data retention. **Requires a formal plan and a data review.**
- **Moves:** relatedness (SDT [S6]), `RETURN_INTENT`.

### D-8. Salience barks at Hades density (Rank 8; folds into D-2 but can ship alone)

- **The fantasy:** "Everything notices what I did."
- **Design:** thousands of short pre-baked reaction lines (room entries, Mira, the captain's taunts) keyed on state predicates and selected by salience with no-repeat memory, which is Hades's lesson [S41]. It generalizes terra_plan2's bank by keying on *state*, not just the room.
- **Risk:** `CALLBACK_TEXT` inflation without mechanics (the causal Goodhart case). Always ship with D-2 or D-3 so the lines have something to reflect.
- **Moves:** V-5, I-1.

### D-9. The Rendered Delve: a tile or pseudo-3D view (Rank 9; substantially changes rendering)

- **The fantasy:** "I *see* the delve." One path is a roguelike grid (tcod or Textual) with a side log. The other is literally a terminal or web raycaster, a Wolfenstein-style first-person corridor view where the Python world is authoritative and text becomes the HUD and log.
- **What it buys:** Romero's readable-space rules [S23] become literal. Students recognize the medium immediately.
- **Costs:** art and content per room, an input model change (real-time or turn-based), and it moves the project away from its research question toward engine work.
- **Risk:** the most expensive direction and the most likely to swallow the design work. **Formal plan required.** Recommended only as a *view* over the same authoritative state, after D-1 proves the loop.

### D-10. Voice-first DM (Rank 10, deferred)

Speech in, speech out, with the Python engine behind a voice narrator. `PLAY_DESIGN.md` already says to defer presentation layers "after the world itself is worth returning to". I agree.

### Why build D-1 and D-2 first

- **D-1 fixes what kills uninvested players first,** with zero LLM risk: the menu, the latency, attack-spam, and forced fights with no warning. It is also the version of the owner's "Doom for D&D" excitement that can be tested within one milestone. Its moddability plank (validated data packs) is exactly the pipeline pre-baked content needs.
- **D-2 fixes what makes players *not care what happens next*:** gaps that never close, junk that is never read, a memory payoff worth one move. It replaces the one hand-coded Mira chain with a generative-but-validated spine that the offline-authored bank can fill.
- **D-3's clocks are small enough to ride along with either** and turn both into real trade-offs.
- **Order:** D-1's data-pack validator becomes D-2's storylet validator, which is why D-1 comes first. Each is independently playtestable with the section 6 protocol.

### Pre-baked versus live: a standing policy [synth]

| Content | Pre-bake (offline, validated) | Live (local model) |
|---|---|---|
| Room entry, combat beats, enemy barks | Yes. State-keyed variants. | No. |
| Clues and reveals | Yes. Fact closure is mandatory. | Never phrases a *new* fact. |
| NPC dialogue for known state combinations | Yes. Salience-selected. | Only for off-graph player inputs, from retrieved fact atoms, with timeout fallback to a banked line. |
| Intent classification (D-6) | – | Yes, schema-constrained, validated by Python. |
| End-of-session chronicle | – | Yes, but after play and citation-gated. Can run on the 24 GB Mac or a frontier model. |

**Budget:** ≤1 live call per 10 player frames, and never on the critical path of movement or combat.

---

## 8. Architecture options (not a decision)

| Option | What it buys | What it costs | Fit with "Python is authoritative" | Student playability | Formal plan? |
|---|---|---|---|---|---|
| **A. Keep and extend the Python terminal engine** (stdlib, current) | Continuity with 53 green tests and the harness; zero install beyond Python; full control; the harness works today. | Hand-rolled parser and rendering. The two-prompt input model needs a refactor (a single-line command parser). | Perfect. | Needs Python and a terminal. Fine for CS students; friction for others. | No, for D-1 and D-3 increments. **Yes** for replacing the input loop, which is a harness-contract change. |
| **B. Textual TUI (still Python)** | Panels (map, clocks, log), mouse and keyboard, and `textual serve` to stream the same Python process to a browser [S57]. | A dependency (breaks stdlib-first; AGENTS.md says a dependency must "clearly earn its keep"). The harness must drive a TUI, or stay on a headless core. | Excellent: same process, same state. | Good. Browser access via a server you host. | Yes (dependency plus harness seam). |
| **C. MUD / Evennia** | Multiplayer, persistence, a web client over websockets, accounts, Django admin [S58]. The natural home for D-7. | A heavy framework, a hosting and ops burden, accounts mean student data, and a rewrite of the world model into Evennia typeclasses. | Good. Python server-authoritative. | Excellent via browser. | **Yes**: hosting, accounts, student data. |
| **D. Inform 7 / TADS / Ink / Twine class** | World-class parser and IF conventions for free (Inform/TADS). Ink is a strong authoring language for branching and storylet-like content, and is designed to "slot into your own game" [S59]. | Inform/TADS put truth in *their* VM, not Python, and LLM integration is awkward. Ink runtime is C#/JS, so a Python port or bridge is needed. Twine is weak for systemic play. | Poor for Inform/TADS/Twine (the authority moves). Ink is compatible *as a content format* evaluated by Python. | Excellent (web-playable). | Yes. It effectively changes the authority engine. |
| **E. Roguelike / ECS engine (python-tcod, an ECS library)** | Grid, field-of-view, entities and components scale well to D-1, D-4 and D-9. A mature roguelike toolchain. | A rewrite of the rendering and world model. ECS is overkill at 10 rooms. | Excellent (Python). | Terminal or SDL window; web needs extra work. | Yes (engine migration). |
| **F. Real-time or graphical engine (Godot, etc.)** | Real visuals, audio, a real "Doom" feel (D-9). | GDScript/C#, so the Python core becomes a sidecar service or is abandoned. Art pipeline. Large scope. | Weak unless Python runs as an authoritative server with Godot as a pure client. | Excellent once shipped. | **Yes**, and it should be a separate project. |
| **G. Web front end for students** (two variants) | **G1, Pyodide:** runs the *same Python engine in the browser* via WebAssembly [S60]. No server, and no student data leaves the machine unless you collect it. **G2, a thin server** (FastAPI/websockets) plus a static client. | G1: no live local LLM, since browsers can't reach Ollama, so **pre-baked content becomes mandatory** (which fits the policy above); the harness replays still work on the pure-Python core. G2: hosting and data handling. | Excellent in both (the same Python core). | Best: a URL. | G1: moderate (packaging only). G2: **Yes** (hosting, data). |

**My read, not a decision [synth]:**
- The research value lives in the Python core and its harness. Keep A as the authoritative core indefinitely.
- Treat every other option as a *front end* or *content format* over it: G1 for classroom reach, B for richer terminal play, Ink or JSON as an authoring format for storylets.
- Do C, E and F only when a direction (D-7 or D-9) has proven its loop in A.

**Choices that require a formal Terra/Astra plan before building:**
- Any change to the input loop that the harness replays through.
- Any new dependency.
- Any change that lets an LLM output select among state-changing options (D-6).
- Any persistent cross-session file (D-4).
- Any networked or multi-user play (C, D-7, G2).
- Any collection of student data beyond de-identified ledger records.
- Any engine migration (D, E, F).

---

## 9. Appendix: the yardstick (one page)

Apply this to any transcript, build, or plan. Each item names the principle and section. Answer Y/N/?, and quote the evidence.

**Consequence (P1, §3 C)**
1. ☐ Does every player-writable state field have at least one reader rule? No `DEAD_STATE`. (S)
2. ☐ For each claimed consequence, does a flipped-decision replay differ in its outcome projection, and not by a trivial amount (`HOLLOW_CONSEQUENCE`)? (M)
3. ☐ When a remembered fact is used, does the output make the causal bridge visible? (J)
4. ☐ Does every takeable object have a use or a reader? (S)

**Curiosity (P2, §3 K)**
5. ☐ Is every anomaly in the text (missing, broken, sealed, silent) registered with a payoff or explicitly marked atmosphere-only? (S)
6. ☐ Does every payoff fact have ≥3 reachable clues? (S)
7. ☐ Is every hidden fact committed by Python before its first clue, and unchanged afterwards? (M)

**Momentum (P3, §3 L)**
8. ☐ Is the first meaningful state change within the first 5 inputs? (M)
9. ☐ Do conventional inputs (`n`, `north`, `x`, `i`, `go`) work at the top prompt? (M)
10. ☐ Is the number of frames with >1.5 s latency ≤ 1 per 20 frames, with 0 over 5 s outside the end-of-session chronicle? (M)
11. ☐ Is input tax ≤ 1.5 frames per state-changing action? (M)

**Decisions (P4, §3 D)**
12. ☐ Does no action exceed 90% share in any repeated decision context (`DOMINANT_ACTION`)? (M)
13. ☐ Is threat size telegraphed before commitment, with an alternative (retreat, avoid, prepare) available? (M/J)
14. ☐ Does the thorough path cost something measurable (time, clock, HP, resource)? (M)
15. ☐ Do character options differ in *verbs or situations*, not just numbers? (S)

**Failure (P5, §3 F)**
16. ☐ Does every non-combat failure change the situation (clock, info, route, attitude)? (M)
17. ☐ Is no failure secretly a success (`FAIL_FORWARD_FAKE`)? (M)
18. ☐ Does death leave something behind (knowledge, legacy, chronicle)? (S)

**Voice (P6, §3 V)**
19. ☐ Do the fact-to-text rules pass on *all* rendered text, static and generated? (M)
20. ☐ Are there zero `DM:` entities, numbers or exits outside the fact packet or allowed lexicon? (M+J)
21. ☐ Is there no praise on failure, no imperatives to the player, no meta leaks? (M)
22. ☐ Is banked texture keyed on state, not only on event and room (anti-oatmeal)? (S)

**Identity (P7, §3 I)**
23. ☐ Is some output in the last two-thirds of a session conditioned on this player's history? (M)

**Measurement hygiene (§5)**
24. ☐ Is the comparison paired (same seed, persona, coverage floor), with intervals reported and no composite score? (§5)
25. ☐ Is the judge a different model family from the builder and narrator, build-blind, and calibrated against human κ for each reported mode? (§5)
26. ☐ Are human findings reported beside machine findings, never summed, with the free-choice measure reported only from humans? (§6)

**The one question (the north star)**
27. ☐ In the human free-choice window, did the player keep going? (§6.2)

---

## 10. Sources

Confidence key: **Read** means I fetched and read the relevant text (or the directly relevant section). **Skimmed** means an abstract, summary page, or search excerpt only. **Unverified** means cited from general knowledge or secondary summaries, and flagged in the text.

| # | Source | URL | Used for | Confidence |
|---|---|---|---|---|
| S1 | Hunicke, LeBlanc, Zubek (2004), *MDA: A Formal Approach to Game Design and Game Research* | https://users.cs.northwestern.edu/~hunicke/MDA.pdf | Designer/player asymmetry; the eight aesthetics (Sensation … Submission); "Discovery" | Read (relevant sections via PDF text) |
| S2 | Loewenstein (1994), "The Psychology of Curiosity: A Review and Reinterpretation," *Psychological Bulletin* 116(1):75–98 | https://www.researchgate.net/publication/232440476_The_Psychology_of_Curiosity_A_Review_and_Reinterpretation | Information-gap theory; curiosity peaks at intermediate knowledge | Skimmed (abstract and secondary summaries) |
| S3 | Kang et al. (2009), "The Wick in the Candle of Learning," *Psychological Science* | https://journals.sagepub.com/doi/abs/10.1111/j.1467-9280.2009.02402.x | Inverted-U curiosity/confidence; curiosity and memory for surprising answers | Skimmed (abstract) |
| S4 | Csikszentmihalyi (1990), *Flow: The Psychology of Optimal Experience* | (book; no URL) | Flow conditions: clear goals, feedback, challenge/skill balance | Unverified (standard reference, not re-read) |
| S5 | Meier, GDC 2012 "Interesting Decisions" (Game Developer write-up) | https://www.gamedeveloper.com/design/gdc-2012-sid-meier-on-how-to-see-games-as-sets-of-interesting-decisions | Criteria for interesting decisions; "err on the side of too much information" | Read (write-up; talk video not watched) |
| S6 | Ryan, Rigby, Przybylski (2006), "The Motivational Pull of Video Games: A Self-Determination Theory Approach," *Motivation and Emotion* 30:347–363 | https://link.springer.com/article/10.1007/s11031-006-9051-8 | Autonomy, competence, relatedness predict enjoyment and future play; PENS lineage | Skimmed (abstract) |
| S7 | Schell, *The Art of Game Design: A Book of Lenses* | https://schellgames.com/art-of-game-design | Lens of Curiosity and Lens of Surprise exist | Skimmed (existence only; exact lens questions not verified) |
| S8 | Sweetser & Wyeth (2005), "GameFlow," *Computers in Entertainment* 3(3) | https://eprints.qut.edu.au/44776/ | Eight GameFlow elements | Skimmed (abstract) |
| S9 | The Alexandrian, "The Three Clue Rule" | https://thealexandrian.net/wordpress/1118/roleplaying-games/three-clue-rule | Three-clue redundancy; proactive and permissive clues | Read |
| S10 | Finch, *A Quick Primer for Old School Gaming* (via Wikipedia and reviews) | https://en.wikipedia.org/wiki/Matthew_J._Finch | "Rulings, not rules"; player skill over character abilities | Skimmed (secondary; primer PDF not read) |
| S11 | Blades in the Dark SRD, "Progress Clocks" | https://bladesinthedark.com/progress-clocks | Visible clocks; obstacle not method; racing and linked clocks | Read |
| S12 | The Alexandrian, "Xandering the Dungeon" (2010; formerly "Jaquaying") | https://thealexandrian.net/wordpress/13085/roleplaying-games/xandering-the-dungeon | Loops and multiple paths enable strategic choice; *Caverns of Thracia* | Read (summary level) |
| S13 | Dungeon World SRD, "Gamemastering" | https://www.dungeonworldsrd.com/gamemastering/ | GM agenda, principles, soft/hard moves, move list; 7–9 partial success | Read |
| S14 | Nelson, *The Craft of Adventure* (2nd ed.), "Bill of Player's Rights" | https://www.ifarchive.org/if-archive/programming/general-discussion/Craft.Of.Adventure.txt | Sixteen player's rights, quoted by item title | Read (downloaded; list extracted verbatim) |
| S15 | Ashwell (2015), "Standard Patterns in Choice-Based Games" | https://heterogenoustasks.wordpress.com/2015/01/26/standard-patterns-in-choice-based-games/ | Choice-structure vocabulary; bottlenecks and choice illusion | Read (summary level) |
| S16 | Bartle (1996), "Hearts, Clubs, Diamonds, Spades: Players Who Suit MUDs" | https://en.wikipedia.org/wiki/Bartle_taxonomy_of_player_types | Four player types | Skimmed (secondary) |
| S17 | Yee (2006), "Motivations for Play in Online Games," *CyberPsychology & Behavior* 9(6):772–775 | https://journals.sagepub.com/doi/10.1089/cpb.2006.9.772 | Achievement, social, immersion components | Skimmed (abstract/secondary); the "not mutually exclusive" claim is from memory |
| S19 | Sylvester (2013), "The Simulation Dream" | https://tynansylvester.com/2013/06/the-simulation-dream/ | The player's mental model as the game; the Ultima Online anecdote; apophenia | Read |
| S20 | Sylvester, GDC 2017 RimWorld talk (Game Developer coverage) | https://www.gamedeveloper.com/design/video-how-i-rimworld-i-found-success-through-ridiculous-contrarian-design | "Story generator" framing | Skimmed |
| S21 | Ryan (2018), *Curating Simulated Storyworlds* (PhD, UCSC) | https://escholarship.org/uc/item/1340j5h2 | Emergent narrative needs curation | Skimmed (abstract and summaries) |
| S22 | Plotkin, Zarfian Cruelty Scale (IFWiki) | https://www.ifwiki.org/Cruelty_scale | Merciful…Cruel definitions | Read |
| S23 | eevee (2015), "You should make a Doom level, part 2," quoting Romero's rules via the Doom Wiki | https://eev.ee/blog/2015/12/30/you-should-make-a-doom-level-part-2/ | Romero's level design rules (flow, landmarks, contrast, secrets, reachable views) | Read (secondary; the Doom Wiki original returned 403) |
| S24 | Game Developer, "The combat design of DOOM" (GDC 2018, Loudy and Campbell, "Embracing Push Forward Combat") | https://www.gamedeveloper.com/design/video-the-combat-design-of-i-doom-i- | Push-forward combat; resources from enemies | Skimmed (write-up; talk not watched) |
| S25 | Wikipedia, "Doom modding" | https://en.wikipedia.org/wiki/Doom_modding | WAD separation; source release Dec 1997, GPL Oct 1999 | Read |
| S26 | Wikipedia, "Dwarf Fortress" | https://en.wikipedia.org/wiki/Dwarf_Fortress | "Losing is Fun"; no victory condition | Skimmed (search excerpt) |
| S27 | Into the Breach GDC 2019 postmortem (Game Developer / Wikipedia coverage) | https://www.gdcvault.com/play/1025772/-Into-the-Breach-Design | Telegraphed attacks; "every death your own fault" | Skimmed (secondary) |
| S28 | RogueBasin, "Berlin Interpretation" (2008) | https://www.roguebasin.com/index.php/Berlin_Interpretation | High-value roguelike factors | Read |
| S29 | idiomdrottning, "Fail Forward is bad for gaming," and related critiques | https://idiomdrottning.org/fail-forward | The case against fail-forward (railroading) | Skimmed (search excerpt) |
| S30 | The Alexandrian, "Rulings in Practice: Gathering Information" | https://thealexandrian.net/wordpress/39651/roleplaying-games/rulings-in-practice-gathering-information | Selective fail-forward example | Skimmed (search excerpt) |
| S31 | Yu et al. (2025), "RPGBench: Evaluating LLMs as Role-Playing Game Engines," arXiv:2502.00595 | https://arxiv.org/abs/2502.00595 | LLMs strong at narrative, weak at mechanics and state | Skimmed (abstract) |
| S32 | Jørgensen et al. (2025), "Static vs. Agentic Game Master AI for Facilitating Solo Role-Playing Experiences," arXiv:2502.19519 | https://arxiv.org/abs/2502.19519 | An agentic GM improved immersion and curiosity | Skimmed (abstract) |
| S33 | Compton, "So you want to build a generator…" (10,000 bowls of oatmeal) | https://galaxykate0.tumblr.com/post/139774965871/so-you-want-to-build-a-generator | Perceptual uniqueness and differentiation | Skimmed (quoted via search excerpt) |
| S34 | Short (2016), "Bowls of Oatmeal and Text Generation" | https://emshort.blog/2016/09/21/bowls-of-oatmeal-and-text-generation/ | Generated text is decorative unless correlated with gameplay | Read |
| S35 | Sharma et al. (2023), "Towards Understanding Sycophancy in Language Models," arXiv:2310.13548 | https://arxiv.org/abs/2310.13548 | Sycophancy is prevalent and linked to preference data | Skimmed (abstract) |
| S36 | Liu et al. (2024), "Lost in the Middle," *TACL* 12:157–173 | https://aclanthology.org/2024.tacl-1.9/ | Mid-context information is used worse (amnesia mechanism) | Skimmed (abstract) |
| S37 | Zhu et al. (2023), "FIREBALL," ACL 2023 | https://aclanthology.org/2023.acl-long.229/ | Structured state improves LLM D&D turns | Skimmed (abstract) |
| S38 | Zhu et al. (2023), "CALYPSO: LLMs as Dungeon Masters' Assistants," AIIDE 19 | https://arxiv.org/abs/2308.07540 | LLM as DM assistant | Skimmed (abstract) |
| S39 | Short (2016), "Beyond Branching: Quality-Based, Salience-Based, and Waypoint Narrative Structures" | https://emshort.blog/2016/04/12/beyond-branching-quality-based-and-salience-based-narrative-structures/ | Storylets, QBN, salience, waypoint | Read (summary level) |
| S40 | Kennedy (2017), "I've stopped talking about quality-based narrative, I've started talking about resource narrative" | https://weatherfactory.biz/qbn-to-resource-narratives/ | Qualities "created equal" regret; scarce, fungible resources | Read (summary level) |
| S41 | Game Developer, "Dive into the dialogue of Hades at GDC 2021," plus press coverage of line counts | https://www.gamedeveloper.com/audio/dive-into-the-dialogue-of-i-hades-i-at-gdc-2021 | ~21,000 voice lines; reactive, non-repeating dialogue | Skimmed (search excerpts; figures from press) |
| S42 | Center for SDT, Intrinsic Motivation Inventory | https://selfdeterminationtheory.org/intrinsic-motivation-inventory/ | IMI subscales; adaptation; academic use; pressured persistence and free choice | Read |
| S43 | Vanden Abeele et al. (2020), "Development and validation of the Player Experience Inventory," *IJHCS* 135:102370 | https://dl.acm.org/doi/10.1016/j.ijhcs.2019.102370 | PXI constructs (functional and psychosocial), enjoyment add-on | Skimmed (abstract and construct list via search) |
| S43b | Haider et al. (2022), "miniPXI," *PACM HCI* 6(CHI PLAY) | https://dl.acm.org/doi/10.1145/3549507 | 11 single items; reliability .51–.83; validity for 9 constructs | Skimmed (search excerpt; ACM page 403) |
| S44 | Manheim & Garrabrant (2018), "Categorizing Variants of Goodhart's Law," arXiv:1803.04585 | https://arxiv.org/abs/1803.04585 | Regressional, extremal, causal, adversarial | Skimmed (abstract) |
| S45 | Medlock et al. (2002), "Using the RITE method to improve products" | https://www.jpattonassociates.com/wp-content/uploads/2015/04/rite_method.pdf | RITE; Age of Empires II tutorial case (10 then 6) | Skimmed (secondary summaries) |
| S46 | Zheng et al. (2023), "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena," NeurIPS D&B | https://arxiv.org/abs/2306.05685 | Position, verbosity, self-enhancement bias; >80% agreement on their task | Skimmed (abstract) |
| S47 | Nielsen (2000), "Why You Only Need to Test with 5 Users" | https://www.nngroup.com/articles/why-you-only-need-to-test-with-5-users/ | 1−(1−L)ⁿ, L≈31%; iterate; ~20 users for quantitative | Read |
| S48 | Faulkner (2003), "Beyond the five-user assumption," *Behavior Research Methods* 35(3):379–383 | https://link.springer.com/article/10.3758/BF03195514 | 5-user sets found 55–99% of problems | Unverified (numbers from secondary summaries; paywalled) |
| S49 | *Games User Research* (Oxford, 2018), think-aloud chapter; and CTA/RTA literature | https://academic.oup.com/book/26677/chapter/195457270 | Concurrent think-aloud reactivity versus retrospective recall loss | Skimmed (search excerpts) |
| S50 | "Employing think-aloud protocols and constructive interaction to test the usability of online library catalogues" (*Interacting with Computers*) | https://www.sciencedirect.com/science/article/abs/pii/S0953543804000839 | Constructive interaction (pairs) as an alternative | Skimmed (title and snippet only) |
| S51 | Law, Brühlmann, Mekler (2018), "Systematic Review and Validation of the GEQ," CHI PLAY | https://research.aalto.fi/en/publications/systematic-review-and-validation-of-the-game-experience-questionn/ | No support for the 7-factor GEQ (N=633); citation problems | Read (abstract page) |
| S52 | "Independent Validation of the Player Experience Inventory," CHI 2024 | https://dl.acm.org/doi/10.1145/3613904.3642270 | Independent PXI validation exists | Skimmed (title only) |
| S53 | 45 CFR 46.104 (eCFR), exempt research | https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-A/part-46/subpart-A/section-46.104 | Exemption (d)(1): normal educational practices | Skimmed (search excerpt of regulation text) |
| S54 | Park et al. (2023), "Generative Agents," UIST | https://dl.acm.org/doi/10.1145/3586183.3606763 | Memory retrieval by recency, importance, relevance; reflection | Skimmed (abstract/secondary) |
| S55 | Grinblat & Bucklew (2017), "Subverting historical cause & effect: generation of mythic biographies in Caves of Qud," FDG | https://www.pcgworkshop.com/archive/grinblat2017subverting.pdf | Generating biographies from event sequences | Skimmed (abstract) |
| S56 | Ollama, "Structured outputs" | https://ollama.com/blog/structured-outputs | JSON-schema-constrained output for local models | Skimmed |
| S57 | Textual (Textualize) | https://textual.textualize.io/ | Python TUI; `textual serve` to browser | Skimmed |
| S58 | Evennia documentation | https://www.evennia.com/docs/latest/Components/Webclient.html | Python MUD with web client | Skimmed |
| S59 | inkle, ink | https://github.com/inkle/ink | Ink as embeddable narrative scripting | Skimmed |
| S60 | Pyodide | https://pyodide.org/ | CPython in the browser via WebAssembly | Skimmed |
| – | Project sources: `DnD_Bot_Interface/AGENTS.md`, `docs/PLAY_DESIGN.md`, `README.md`, `docs/DND_0_6_STEVE_PLAYTEST.md`, `dnd_combat/*.py`, `tests/*`; Ivy dossiers `terra_playtest.md`, `terra_plan2.md` | local | The game's thesis, constraints, current behavior, and plans; all **[obs]** claims | Read (the [obs] claims were probed read-only on 2026-09-28) |

*Not consulted, though suggested in the brief:*
- Amy Jo Kim's playtesting practice.
- Tracy Fullerton's *Game Design Workshop* playtesting chapter. Only its existence and its coverage of think-aloud were confirmed, via search.
- The PENS item set, which is reportedly proprietary.
- Brogue design specifics. Brian Walker's talks were located but not reviewed.
- Inform 7 and TADS documentation. Claims about them in section 8 are general practitioner knowledge **[lore]**.
