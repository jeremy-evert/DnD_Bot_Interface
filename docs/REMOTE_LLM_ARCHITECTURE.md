# Remote LLM Architecture

## Goal

Run the language model on a remote GPU while keeping the D&D game engine authoritative and lightweight on the player's machine.

The remote model should be treated as an **imagination service**, not as the owner of the campaign.

## Existing capability

The current narrator already talks to an OpenAI-compatible chat-completions endpoint.

Default:

```text
http://localhost:8080/v1/chat/completions
```

Override it with:

```sh
export DND_NARRATOR=local
export DND_LLM_ENDPOINT="http://REMOTE_HOST:8080/v1/chat/completions"
export DND_LLM_MODEL="MODEL_NAME_EXPOSED_BY_SERVER"
python3 -m dnd_combat
```

That means a school GPU, research cluster, desktop workstation, or other remote server can eventually replace the local MLX server without changing the game-engine boundary, provided the endpoint is reachable and OpenAI-compatible.

## Recommended topology

```text
phone / Chromebook / laptop
        |
        v
terminal or future UI
        |
        v
Python game engine
  - rules
  - dice
  - world state
  - inventory
  - hidden truth
  - validation
        |
        v
LLM adapter
        |
        v
secure network path
        |
        v
remote OpenAI-compatible inference server
  - narration
  - NPC dialogue
  - intent interpretation
  - validated creative proposals
```

The client should keep enough state to continue deterministic play if the remote model disappears.

## Principle: remote compute, local authority

Moving the model to a server must not move game sovereignty with it.

The remote model receives the smallest useful factual packet for the current job.

Examples:

### Narration request

Send:

- event type
- already-resolved facts
- deterministic plain text

Do not send:

- unrelated hidden facts
- entire campaign history when unnecessary
- secrets the narrator does not need

### NPC dialogue request

Eventually send:

- NPC identity and voice notes
- facts that NPC knows
- relevant memories
- current attitude and goal
- visible scene facts

Do not send secrets the NPC should not know.

### Intent interpretation request

Eventually send:

- player utterance
- visible room facts
- available deterministic actions
- possibly relevant inventory

The model proposes an interpretation. Python accepts, rejects, or asks for clarification.

## Why this layout is useful

### 1. The front end stays cheap

A Chromebook or small laptop can run the game while the expensive matrix multiplication happens elsewhere.

### 2. The game survives model failure

The current adapter already falls back instead of blocking ordinary play. That behavior should remain sacred.

### 3. Models become swappable

If two servers expose compatible chat-completions APIs, the engine should not care whether the backend is:

- MLX on a Mac
- llama.cpp
- vLLM
- another OpenAI-compatible inference server
- a research-cluster deployment

### 4. Hidden state can stay private from the narrator

A remote narrator does not need to know every secret in the world. Limiting context improves both game integrity and prompt efficiency.

## Security note

The current HTTP adapter sends only a `Content-Type` header. It does **not** currently add an API key or authorization header.

Therefore, do not expose the existing inference endpoint directly to the public internet.

For experiments, prefer a protected path such as:

- campus/private network
- VPN
- SSH tunnel
- reverse proxy with authentication
- another authenticated gateway

If remote inference becomes a regular feature, add optional authentication to the adapter as its own small milestone with deterministic tests.

## Suggested environment contract

Keep configuration in environment variables rather than machine-specific code:

```sh
DND_NARRATOR=local
DND_LLM_ENDPOINT=http://host:8080/v1/chat/completions
DND_LLM_MODEL=model-name
DND_NARRATOR_DEBUG=1
```

Possible future additions:

```text
DND_LLM_API_KEY
DND_LLM_TIMEOUT
DND_LLM_PROVIDER
```

Do not add them until a real deployment requires them.

## Remote server requirements

A candidate backend should be judged on a few practical questions:

| Question | Why it matters |
| --- | --- |
| Does it expose OpenAI-compatible chat completions? | Keeps the game adapter simple. |
| Is first-token latency acceptable? | Dialogue dies when every sentence feels like a loading screen. |
| Can thinking/reasoning be disabled when unnecessary? | Narration should spend tokens on visible output. |
| Can it return reliable JSON? | Structured proposals must cross a validated boundary. |
| Can the endpoint be secured? | The model server should not become a public GPU vending machine. |
| Can it recover cleanly after failure? | The game must keep moving. |

## Latency budget philosophy

Not every action deserves an LLM request.

Use remote inference for moments where creativity pays rent:

- first or important room entry
- NPC dialogue
- unusual player intent
- major success or failure
- revelation
- victory or death
- occasional world events

Keep routine mechanics local:

- ordinary movement
- attack rolls
- damage
- inventory bookkeeping
- simple command aliases
- status
- deterministic look output

A fast boring line is better than a beautiful four-second pause after every sword swing.

## Context strategy

Avoid sending a giant transcript forever.

Future context should be assembled from structured state:

```text
current scene
+ relevant player state
+ relevant NPC memory
+ relevant discovered facts
+ recent important events
= model context
```

This makes long campaigns possible without pretending that an ever-growing chat log is a database.

## Persistence strategy

For now, Python objects are enough.

When persistence exceeds what in-memory state can comfortably handle, move durable world state into a simple store. SQLite is the likely first candidate because it is:

- local
- transactional
- standard and boring in the good way
- easy to inspect
- enough for a single-player campaign

Do not add a database merely because databases exist.

## Evaluation experiments

When remote inference is available, compare backends using the same saved prompts and game states.

Measure:

- response latency
- malformed JSON rate
- factual invention rate
- rule-boundary violations
- dialogue quality
- narration concision
- whether the response creates curiosity
- whether fallback remains invisible to gameplay

A larger model is not automatically the better Dungeon Master component.

The winning backend is the one that improves play without stealing control from the engine.

## Immediate recommendation

Finish and playtest D&D 0.6 first.

At the same time, the existing `DND_LLM_ENDPOINT` seam is already good enough for a controlled remote-server experiment. Point it at a protected OpenAI-compatible endpoint and treat the server as replaceable compute.

The architecture should remain:

> **Python remembers what is true. The remote model helps make truth interesting.**
