# Play Design: Building a Tiny World That Feels Alive

## Research question

> Can a small artificial world make the player genuinely curious about what happens next?

The project is not trying to prove that an LLM can produce fantasy prose. That is easy.

The harder and more interesting problem is whether a deterministic game engine plus a creative language model can produce the feeling that makes tabletop role-playing games memorable: **I made a choice, the world changed because of it, and now I need to know what happens next.**

## Core design principle

> D&D is not primarily a story generator. It is a consequence generator.

The story is what the player remembers afterward.

A good session usually grows from a repeating loop:

1. **Tension** - something demands attention.
2. **Choice** - the player can meaningfully decide what to do.
3. **Consequence** - the world changes, including when the attempt fails.
4. **Revelation** - the player learns something new.
5. **Reward** - the player gains progress, leverage, knowledge, identity, or sometimes loot.
6. **New tension** - the altered world presents another problem or opportunity.

The LLM should strengthen that loop, not replace it.

## What tends to make play fun

### 1. Agency

The player should be able to attempt things the designer did not pre-script.

The engine does not need to guarantee success. It needs to distinguish between:

- impossible
- possible but risky
- possible and straightforward

Future natural-language interpretation should map unusual intent onto deterministic actions or checks. It should not allow prose to bypass rules.

### 2. Uncertainty

The player should not know every outcome in advance.

Useful sources of uncertainty include:

- dice
- unexplored spaces
- NPC motives
- hidden facts
- incomplete information
- random world events
- consequences that unfold later

The model should not be allowed to quietly rewrite hidden truth to make every scene narratively convenient.

### 3. Persistent consequences

A good world remembers.

Examples:

- an object taken from one room remains gone
- an NPC notices what the player is carrying
- a defeated enemy stays defeated
- a shortcut remains opened
- a character remembers an insult or favor
- a choice changes what becomes possible later

Persistence is more important than descriptive richness.

### 4. Discovery

Exploration should reveal things the player did not already know.

Discovery can be:

- geography
- lore
- a relationship
- a mechanical advantage
- an NPC secret
- a hidden connection between earlier details
- a new use for an ordinary object

A room that exists only to contain prose is weak. A room that changes the player's understanding of the world earns its existence.

### 5. Meaningful failure

Failure should not simply mean "nothing happens."

Good failure may:

- cost time
- create noise
- consume a resource
- damage a relationship
- expose information
- move an enemy
- close one path and open another
- create a new problem

The dice should occasionally make the story worse in a way that makes the game better.

### 6. Identity and progression

The player should gradually become somebody in the world.

Progression is more than levels and equipment. It can include:

- reputation
- relationships
- favors owed
- enemies made
- places discovered
- recurring habits
- personal history
- a recognizable play style

This is one area where persistent LLM-assisted NPC memory may eventually be especially valuable.

### 7. Pacing

Not every moment deserves equal detail.

A useful scene director should eventually distinguish among:

- **play it out** - danger, uncertainty, negotiation, discovery
- **summarize it** - uneventful travel, repeated routine
- **skip it** - nothing changed and no decision matters

The system should not spend 500 tokens describing breakfast unless breakfast contains a decision, clue, threat, joke worth keeping, or an assassin.

### 8. Surprise

Surprise should come from the world, not only from model improvisation.

Future sources may include:

- deterministic encounter tables
- seeded random events
- NPC plans
- faction movement
- weather or time pressure
- hidden clocks
- model-generated color validated through Python

The goal is for the player to occasionally think, "I did not expect that, but it makes sense."

## Division of authority

### Python owns truth

Python remains authoritative for:

- dice
- checks and combat
- HP, death, and victory
- inventory
- movement and exits
- persistent objects
- deterministic encounters
- hidden game facts
- state changes
- validation of LLM proposals

### The LLM owns expression and interpretation

The LLM may eventually help with:

- concise narration of resolved events
- NPC dialogue
- mundane room dressing
- interpreting unusual player intent
- phrasing clues whose factual content comes from Python
- character voice
- compression and pacing suggestions

### The LLM never becomes sovereign

The LLM must not directly:

- create mechanical rewards
- add exits
- change HP
- decide dice
- resurrect or kill characters
- rewrite established facts
- secretly alter unresolved truth to fit a story
- mutate persistent state without validation

The useful rule remains:

> The LLM may invent things, but once Python accepts them, Python has to make them real.

## D&D 0.6 playtest hypotheses

The 0.6 map expansion should be treated as an experiment, not merely "more rooms."

### Hypothesis A: geography creates memory

A branch, loop, and optional dead end should create enough spatial structure that revisiting a location feels meaningful.

**Evidence to watch for:** the player remembers where something happened and intentionally returns.

### Hypothesis B: carried junk can become interesting

Mundane objects become fun when the world notices them.

**Evidence to watch for:** the player deliberately carries an odd object because it might matter later.

### Hypothesis C: quiet rooms improve contrast

Not every room should attack the player.

**Evidence to watch for:** noncombat spaces create curiosity, relief, decisions, or conversation instead of feeling empty.

### Hypothesis D: NPC recognition creates consequence

At least one NPC should be able to react to deterministic world state such as inventory, prior events, or encounter outcomes.

**Evidence to watch for:** the reaction feels earned because the engine can explain exactly why it happened.

### Hypothesis E: LLM scenery must create texture without false affordances

Decorative objects can make a room feel inhabited, but they should not accidentally imply mechanics the engine cannot support.

**Evidence to watch for:** scenery improves atmosphere without repeatedly making the player ask to do impossible things.

## Human playtest notes to capture

After a run, write down:

- What made me curious?
- What decision did I actually think about?
- What surprised me?
- What did I remember from an earlier room?
- Did I carry anything weird on purpose?
- Did an NPC or room react to something I had done?
- Where did narration feel slow?
- Where did the world feel fake?
- What did I try that the interface could not understand?
- Did I want to keep playing after the nominal objective was complete?

The strongest metric is not prose quality.

It is:

> **Did I want to see what happened next?**

## Post-0.6 experiment queue

These are design candidates, not current implementation requirements.

### Candidate: intent interpreter

Let the player type natural language such as:

- "I wedge the bent spoon under the door."
- "I show the ring to the old woman."
- "I listen before going north."

The LLM may classify or propose intent, but Python decides whether an action exists, what check applies, and what state changes.

### Candidate: NPC memory

Give important NPCs a small structured record:

- goals
- attitude
- known facts
- memories of player actions
- current plan

Do not run dozens of autonomous agents continuously. Update NPC state only when the world gives them a reason to change.

### Candidate: hidden world state

Introduce facts the narration model does not need to see until relevant:

- culprit identity
- unrevealed room contents
- NPC secrets
- event clocks
- future consequences

This protects discovery from becoming improvised retroactively.

### Candidate: event oracle

Allow occasional deterministic or seeded events to disturb the world.

The oracle changes state first. The LLM narrates the result second.

### Candidate: richer progression

Track narrative progress alongside mechanical progress:

- reputation
- relationships
- discovered facts
- faction standing
- recurring consequences

### Candidate: voice and richer interface

Voice, GUI, character portraits, and virtual-table features are presentation layers. They become valuable after the world itself is worth returning to.

## Design north star

Build the smallest world that can remember the player.

Then make that memory matter.
