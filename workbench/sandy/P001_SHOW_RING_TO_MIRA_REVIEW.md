# P-001 Brenda pilot review: show the ring to Mira

**Review date:** 2026-09-27  
**Penny unit:** [`p001_show_ring_to_mira.json`](../penny/units/p001_show_ring_to_mira.json)  
**D&D baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`

## Brenda run evidence

- **Run ID:** `20260927T204400Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260927T204400Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260927T204400Z-dnd-p001-show-ring-to-mira`
- **Terminal state:** `ENVIRONMENT_FAILURE`
- **Failure:** Brenda's first model request to its configured OpenAI-compatible endpoint at `127.0.0.1:8080` received connection refused. Brenda recorded no model action, tool call, proof, or candidate change.
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260927T204400Z-dnd-p001-show-ring-to-mira/`
- **Worktree base:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Worktree Git status:** clean; no changed or untracked paths.
- **Diff:** empty.

The receipt directory contains `events.jsonl` and `final.json`. There are no raw model-response or Brenda proof receipts because the run stopped at the initial connection attempt.

## Sandy independent decision: FAIL

**Question:** Did Brenda build what Penny specified?

**Finding:** No candidate was built, so Penny's contract is unsatisfied. This is an environment failure, not evidence of an implementation or scope failure.

Sandy freshly ran Penny's exact proof command in Brenda's isolated worktree:

```text
Command: python3 -m unittest discover -v
Started: 2026-09-27T20:44:33Z
Finished: 2026-09-27T20:44:34Z
Exit: 0
Result: 37 tests passed
```

The green suite verifies the unchanged baseline only. It does not turn the missing implementation into a pass.

## Annabelle local correction

**Destination:** Brenda pilot runtime readiness, not the D&D architecture, Brenda policy, or Brenda tool adapter.

**Evidence:** The expected Brenda service at `http://127.0.0.1:8080/v1/chat/completions` refused a connection. The Brenda virtual environment and the active `python3` do not have `mlx_lm` installed. The requested OptiQ model is already cached locally, so this run did not attempt a download. Brenda returned its existing `ENVIRONMENT_FAILURE` terminal state with a timestamped receipt.

**Correction:** Before the next Brenda run, make an already available, compatible OptiQ chat-completions service reachable at `127.0.0.1:8080`, or configure `BRENDA_ENDPOINT` to the active compatible service. Confirm the endpoint is ready before relaunching. No Brenda code or policy change is supported by this failure.

## Next clean rerun

After the endpoint is available, rerun the same Penny unit with the same `base_ref`. Brenda must create a new isolated worktree and run ID; preserve the failed worktree evidence and receipts, then remove the disposable worktree before rerunning. Sandy then reruns the proof commands with fresh timestamps and checks the new diff and changed paths against Penny's write scope. Do not hand-repair or relabel a historical worktree as a pass.

## Pilot policy observations

- **Penny:** The one-intent boundary and explicit paths, proof, step limit, and baseline made a concrete bounded unit.
- **Sandy:** A passing baseline suite is not proof of implementation; terminal state and diff evidence remain decisive.
- **Annabelle:** An initial connection refusal warrants environment readiness work. It does not justify an architecture change.

## User-directed OptiQ bootstrap and fresh rerun

The endpoint was initially down. The local `mlx_server` root was resolved at runtime, and its existing `scripts/mlx-server start 35b` path was used. The provisioned 35b profile maps to `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit-REAP-19B`; no model download or install was attempted.

The first launcher invocation did start the server and load the model, but returned exit 1. Direct verification returned HTTP 200 from `/v1/models` and included the expected OptiQ model. Inspection found two local Screen compatibility defects in `scripts/mlx-server`: this Screen build rejects `-Logfile`, and `screen -list` returns 1 while printing a normal detached session, which combined with `pipefail` caused the script to misreport the session as stopped. The launcher was adjusted to configure its `.runtime/server/screenlog.0` through a generated Screen config and to inspect the complete session listing without relying on Screen's nonzero status. Afterward, `scripts/mlx-server status` exited 0 and showed the expected model. `bash -n`, status, and `git diff --check` passed.

Startup evidence, including the launcher stdout, launcher metadata, `/v1/models` response, verification record, and a copy of the server screen log, is preserved in:

```text
/Users/evertj/git/mlx_server/.runtime/hanna-optiq-bootstrap-20260927T223240Z/
```

### Fresh Brenda run

- **Unit:** same file and exact content as the first attempt; SHA-256 `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Run ID:** `20260928T022402Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260928T022402Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260928T022402Z-dnd-p001-show-ring-to-mira`
- **Model:** `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit-REAP-19B`
- **Terminal state:** `ENVIRONMENT_FAILURE`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260928T022402Z-dnd-p001-show-ring-to-mira/`

Brenda read the nine authorized files. At step 10 it attempted to read `dnd_combat/matching.py`; the tool rejected that out-of-scope path, so no file contents were returned. The next OptiQ response included explanatory prose followed by an invalid, over-escaped JSON `write_file` action. Brenda's action parser rejected it before any write or proof action. No candidate files were changed: the worktree is still clean at the pinned base, with an empty diff and no untracked paths.

Sandy freshly ran the exact proof command in this worktree:

```text
Command: python3 -m unittest discover -v
Started: 2026-09-28T02:28:42Z
Finished: 2026-09-28T02:28:42Z
Exit: 0
Result: 37 tests passed
```

**Sandy decision: FAIL.** The tests pass on the unchanged baseline, but there is no implementation to compare with Penny's contract.

### Annabelle correction after this FAIL

**Destination:** Brenda's model-action protocol and failure receipts.

**Evidence:** Brenda's system prompt already requires exactly one JSON action. OptiQ returned a prose preamble and malformed escaped JSON; `brenda.model._parse_action` raised `ModelError` before the response could be written as a `raw/model_*.txt` receipt. `runner.py` classifies all `ModelError` cases as `ENVIRONMENT_FAILURE`, including invalid model actions. The denied `matching.py` read is separately recorded as a tool error and did not expose that file or modify the worktree.

**Proposed correction:** Preserve the raw model response before parsing; distinguish transport failures from malformed action output; and, for malformed output, provide the parser error and rejected response to Brenda for a bounded retry inside the existing `max_model_steps` budget. If the bounded retry still fails, report a model-protocol failure instead of an environment failure. Keep all tool scope checks unchanged. Inspection of the provisioned MLX server source did not reveal `response_format` or JSON-schema handling, so this proposal does not depend on a structured-output option that this local server may not support.

After this Brenda-side correction is accepted and applied, rerun the exact same Penny unit and baseline in a new worktree. Preserve both failed worktrees and receipts as historical evidence; do not hand-repair either run.

## Brenda protocol correction commit and next failure

The response-protocol correction was implemented and committed in `brenda_the_builder` as `851104db0738ae2a1c04b6d66b89f14948705713` (`Recover from invalid model action responses`). Brenda's suite passed 16 tests, including tests for malformed response receipts, bounded retry, protocol exhaustion, transport classification, and terminal-state selection.

The next run used the unchanged Penny unit (SHA-256 `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`) and exact baseline `a7d2760045a46f6b992535a9141ed3a8f74596d9`:

- **Run ID:** `20260928T034333Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260928T034333Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260928T034333Z-dnd-p001-show-ring-to-mira`
- **Terminal state:** `FAILED`; `model_done: false`; model step budget exhausted.
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260928T034333Z-dnd-p001-show-ring-to-mira/`

Steps 1–9 read the nine Penny-authorized files. Steps 10–15 each attempted another unauthorized read (`matching.py`, `commands.py`, `world.py`, `session.py`, `terminal.py`, and `combat.py`); the tool rejected each request without returning file contents. Step 16 returned malformed JSON, which the new code preserved at `raw/model_016.txt` and recorded as `model_protocol_error`. With the unit's fixed 16-step budget exhausted, Brenda could not retry or implement anything. Git reality is clean at the pinned baseline: no changed or untracked paths and an empty diff.

Sandy reran the exact proof command in this worktree:

```text
Command: python3 -m unittest discover -v
Started: 2026-09-28T03:48:43Z
Finished: 2026-09-28T03:48:43Z
Exit: 0
Result: 37 tests passed
```

**Sandy decision: FAIL.** No implementation exists; the green proof is the unchanged D&D baseline.

**Annabelle process correction:** Brenda spends model steps selecting reads even though Penny has already enumerated the authorized read paths, then continued spending steps after each rejected out-of-scope request. Change the runner script to pre-read and receipt exactly Penny's `read_paths` before the first model call, providing those source contents as the bounded build context. Keep the read/write scope checks in `BrendaTools`; make a denied out-of-scope read or write stop the run immediately as `FAILED`. This is deterministic harness behavior, not a change to Penny's unit or another model prompt strategy. Test preflight receipts/context, immediate scope-stop, and the existing protocol-retry path, then retry the same unit and baseline in a fresh worktree.

This process correction was committed in `brenda_the_builder` as `d5bc7ed7cbe286bf1b317f460488473de55dc909` (`Preload authorized work unit context`). The runner now receipts and supplies exactly Penny's explicit `read_paths` before model step 1, and a blocked out-of-scope action ends the run immediately. Brenda's suite passed 17 tests. The unchanged Penny unit and D&D base commit were retained. Failed Brenda worktrees were removed only after their receipts and findings were preserved.

## Brenda preflight and bounded-response correction, attempt 4

After commit `d5bc7ed7cbe286bf1b317f460488473de55dc909`, Brenda ran the unchanged Penny unit and pinned baseline in another fresh worktree:

- **Run ID:** `20260928T035234Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260928T035234Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260928T035234Z-dnd-p001-show-ring-to-mira`
- **Terminal state:** `FAILED`; all 16 model steps were consumed.
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260928T035234Z-dnd-p001-show-ring-to-mira/`
- **Base:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`

The preflight delivered all nine authorized source files before step 1, so no read calls or scope violations occurred. Steps 2–3 and 5–16 were rejected malformed responses. Each of those 14 raw responses was the same 2,093-byte partial `write_file` action targeting `dnd_combat/__main__.py`, ending mid-expression (`while game.in`) and lacking the closing JSON. Brenda accepted one complete response at step 4 and wrote `dnd_combat/intent.py`; the candidate has a double-escaped regex (`\\s` in the Python raw pattern), so the required input `I show the ring to Mira` returns `None`. This is a concrete contract failure; the other 13 responses show the server is truncating longer generated output.

Sandy independently ran the exact Penny proof command in this worktree:

```text
Command: python3 -m unittest discover -v
Exit: 0
Result: 37 tests passed
```

Sandy also checked the contract sample directly against the candidate: `interpret_proposal('I show the ring to Mira')` returned `None`. **Sandy decision: FAIL.** The green suite covers only unchanged baseline tests; the candidate fails Penny's required intent and adds no acceptance tests. Git recorded only the authorized `dnd_combat/intent.py` path, with no out-of-scope changes.

### Annabelle correction: request complete action outputs

The repeated identical 2,093-byte JSON prefixes end at a mid-file code token. Brenda's request did not set an output-token limit or disable Qwen thinking, while the local MLX repository's OptiQ scripts explicitly send both `max_tokens` and `chat_template_kwargs: {"enable_thinking": false}`. Correct Brenda's local chat-completions request deterministically to disable thinking and allocate a sufficient bounded completion budget (8,192 tokens), with a unit test asserting those request fields. This changes the transport harness only, leaves Penny's fixed 16-step unit unchanged, and will be committed before the next fresh-worktree attempt.

### Annabelle corrections committed for attempt 5

Brenda now sets a bounded 8,192-token completion budget and disables Qwen thinking in its chat-completions request. A regression test checks both request fields. This addresses the repeated identical partial JSON outputs from attempt 4.

Brenda also now performs a readiness check before any model call, stores `/v1/models` evidence under the run's `bootstrap/` receipts, and skips startup when the expected model is already advertised. If a local endpoint is unhealthy, it discovers a nearby `mlx_server` repository (or accepts `BRENDA_MLX_SERVER_ROOT`), calls that repository's existing `scripts/mlx-server start 35b`, runs `status`, and verifies `/v1/models` and the expected model again. The start process has Hugging Face offline flags set so a missing cache cannot trigger an implicit model download. Non-local endpoints are never used to start a local service.

The Brenda test suite passed 21 tests. These changes were committed locally, without push, as:

- `a6a73fe` — `Bound OptiQ action completions`
- `7e492d8` — `Bootstrap local OptiQ before Brenda runs`

The failed attempt 4 worktree and branch will be removed after its complete raw responses, candidate, proof result, diff, and Sandy decision have been preserved above and in the referenced receipt directory. The next run uses a newly created worktree from the same `a7d2760045a46f6b992535a9141ed3a8f74596d9` baseline and the same unchanged Penny unit.

## Brenda self-bootstrap and complete-output attempt 5

Brenda's durable pre-call readiness and response-budget corrections were exercised in a fresh worktree from the exact same baseline and unit:

- **Run ID:** `20260928T040508Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260928T040508Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260928T040508Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260928T040508Z-dnd-p001-show-ring-to-mira/`

Brenda checked `/v1/models` before its first model call, receipted HTTP 200 and the expected OptiQ model, and skipped local startup because the endpoint was healthy. It preloaded all nine Penny-authorized source files. The 8,192-token non-thinking request produced complete 13 KB and 8 KB source-file actions, fixing the prior 2,093-byte truncation. Brenda wrote only the unit's authorized implementation and test paths.

The first Penny proof had three intent failures and two test errors. Brenda revised the candidate and reran proof; the second proof reduced this to one intent failure and two test errors. Sandy independently reran the exact command and got the same result: **53 tests, 1 failure, 2 errors; FAIL.** The candidate is therefore not acceptable yet.

At model step 14, Brenda's request timed out after the MLX server logged a Metal `Insufficient Memory` error in prompt-cache evaluation. Brenda stopped with `ENVIRONMENT_FAILURE` before a terminal action. The service remained alive and advertised the expected model over HTTP 200 at `/v1/models`; `scripts/mlx-server status` also succeeded. This exposed a second deterministic harness issue: long assistant source-file outputs and full proof output remain in the conversation history across steps, growing the local server's cached context until the 35B process runs out of memory.

### Annabelle correction before retry

Compact Brenda's in-flight conversation deterministically: preserve full raw actions, tool output, and proof output in receipts, but send a bounded execution ledger back to the model rather than replaying prior full source-file writes and full test logs. Keep recent actionable failure details (especially failing test names and tracebacks), the Penny source context, and prior completed paths. Reduce the output ceiling to a still-sufficient 4,096 tokens. Add tests that large prior action payloads are not sent again and proof failures remain available in bounded feedback. The timed-out server can be recovered through the local `mlx-server stop` then existing `start 35b` path, with offline flags and fresh endpoint/model verification. Retry only after preserving this failure and removing its disposable worktree/branch.

### Annabelle recovery and bounded-history correction committed for attempt 6

Brenda now retains complete model responses and tool/proof output in the run receipts while rebuilding each subsequent request from Penny's source context plus a compact execution ledger. Proof feedback keeps the final failure/traceback details and is capped; the ledger itself has a fixed character ceiling. Model responses use `max_tokens: 4096` with thinking disabled. On a transient local model transport failure, Brenda records the failure, runs `scripts/mlx-server stop`, the existing `scripts/mlx-server start 35b`, and `status`, verifies `/v1/models` again, then retries that same unit step once. Startup/recovery commands run with Hugging Face offline flags. Non-transient errors and non-local endpoints do not trigger service restart.

The Brenda suite passed 25 tests, including checks for readiness bootstrap receipts, offline restart, one bounded same-step retry, compact action history, retained proof failure details, and bounded ledger size. These changes are ready to commit locally before the next fresh D&D worktree. The attempt 5 receipts preserve its OOM, two proof outputs, and all authorized candidate paths; its worktree and branch will be removed before rerun.

The recovery and bounded-history correction is committed in `brenda_the_builder` as `12d12ba` (`Bound local OptiQ retries and conversation history`). Brenda's complete test suite passed 26 tests. Before attempt 6, the wedged local inference process is being recycled with the same offline `stop`/`start 35b` path; that recovery is receipted alongside attempt 5's model timeout. No D&D change is being committed, merged, or pushed.

### Attempt 5 recovery gate

The offline recovery helper preserved `stop`/`start` evidence under `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260928T040508Z-dnd-p001-show-ring-to-mira/transport-recovery/manual-before-attempt6/`. The repository's `scripts/mlx-server stop` exited 0 and removed its named Screen session. `scripts/mlx-server start 35b` then exited 1 with `Port 8080 is occupied; refusing to replace another service.` The script's `status` says `Stopped`; Screen has no sessions; both `/v1/models` and chat-completions now close with `RemoteDisconnected`.

`lsof` identifies PID 20725 as a Python listener on `127.0.0.1:8080`, with cwd `/Users/evertj/git/mlx_server` and the MLX core library loaded from that repository's `.venv`. `mlx_server/AGENTS.md` says to protect service sessions and that `stop` must target only this repository's named Screen session. That named session is absent. No direct signal was sent to the PID. A human decision is required to authorize terminating this verified orphaned local server process so the existing offline `start 35b` path can restore OptiQ and the next exact-unit run can proceed.

### Orphan recovery completed and made durable

After Jeremy explicitly authorized SIGTERM of PID 20725, `scripts/mlx-server ensure-running 35b` re-verified the PID immediately before signaling it. The owner check confirmed one listener, bound only to `127.0.0.1:8080`, with cwd equal to the `mlx_server` checkout and its `.venv` MLX core loaded. The script sent SIGTERM, waited for port release, then used the existing `start 35b` path with Hugging Face offline flags. Startup and follow-up `status` both succeeded; `/v1/models` advertised the exact expected OptiQ model. Full stdout/stderr, command exits, model response, and ownership diagnosis are preserved under the attempt 5 `transport-recovery/manual-before-attempt6/` receipt directory.

The durable `ensure-running` path positively classifies the sole listener using `lsof`, requires the exact repository cwd, the configured virtualenv's `site-packages/mlx/core` runtime, and a loopback-only socket. It refuses multiple PIDs, non-loopback bindings, foreign cwd/runtime, and any listener it cannot identify. The existing `stop` command remains limited to the named Screen session. Six ownership tests pass for owned, absent, ambiguous, foreign, non-loopback, and missing-runtime cases. `bash -n`, `scripts/mlx-server status`, and a healthy `ensure-running 35b` check pass. This MLX safety fix is being committed separately from Brenda's local commits.

## Brenda safe-orphan recovery and bounded-history attempt 6

After the orphan was safely recovered and the durable recovery command was committed, Brenda launched a fresh worktree from the pinned baseline with the same unit:

- **Run ID:** `20260928T113212Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260928T113212Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260928T113212Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260928T113212Z-dnd-p001-show-ring-to-mira/`

Pre-call bootstrap saw HTTP 200 and the expected OptiQ model, then preloaded all nine read paths. The local server stayed up through all 16 steps, without another memory error. Brenda's only changed path is the authorized new file `dnd_combat/intent.py`. Steps 1–3 tried to read that not-yet-created write target; step 5 produced a malformed action; steps 4 and 6–16 repeatedly rewrote only `intent.py`. It did not update `dnd_combat/__main__.py` or add tests, and did not issue a `done` action. Terminal state: `FAILED`, `model_done: false`, step budget exhausted, scope clean.

Sandy independently reran `python3 -m unittest discover -v` at `2026-09-28T11:47:40Z`; **37 baseline tests passed**. That green result does not verify this unit: there are no new tests and the new resolver is not connected to the terminal. A direct probe of `resolve_intent('I show the ring to Mira')` returns `talk`, but the required gallery/free-text path remains unimplemented. **Sandy decision: FAIL.** Independent proof output and timing are in `sandy-proof-independent.txt` in the receipt directory. The intent candidate SHA-256 is `44a873e98515b4de0b2cea63ec9da89c130e13e1f3e6db26e28e882428216f6c`.

### Annabelle correction before attempt 7

The compact ledger successfully reduced runaway cache growth, but was too lossy about a generated write target: Brenda could not inspect the resolver it had just created and repeatedly rewrote it instead of integrating it. Preserve full receipts as before, allow Brenda to reread a path it has successfully written during this run, and include the latest generated content for each write-only target in the bounded progress context (replace older content for that same path). Continue to reject reads of untouched write-only paths and any path outside Penny's scope. Add tests for read-after-own-write, refusal before first write, and replacement of stale versions in the compact ledger. Then remove this failed worktree/branch and rerun the same unit from the same baseline.

The write-only readback and latest-generated-content correction passed 29 Brenda tests and is committed locally as `203d731` (`Give Brenda bounded feedback on generated files`). Brenda now rejects readback of untouched write-only files, permits reading a path after a successful in-run write, and includes the latest version of each generated write-only target in the bounded progress context. Complete action contents remain in receipts. The attempt 6 worktree and branch have been removed after preserving its evidence. Attempt 7 will use a new worktree from the same pinned baseline.

## Attempt 7: denied read ended a recoverable run

Brenda used a fresh worktree for the unchanged Penny unit and pinned D&D baseline:

- **Run ID:** `20260928T115120Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260928T115120Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260928T115120Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260928T115120Z-dnd-p001-show-ring-to-mira/`

OptiQ preflight confirmed the expected model before the first model call. At step 1 Brenda tried to read its not-yet-created write-only `dnd_combat/intent.py`; the tool returned a no-content hint to write it first. At step 2 it requested the out-of-scope `dnd_combat/commands.py`. No content was disclosed and no files changed, but the runner treated this read request as a terminal scope violation. Brenda stopped after two model steps, with no candidate changes.

Sandy independently ran the exact proof command at `2026-09-28T11:53:10Z`: `python3 -m unittest discover -v` passed all 37 unchanged baseline tests. This is not evidence of the requested candidate behavior; the candidate is missing. Sandy decision: **FAIL**. Independent output is preserved at `sandy-proof-independent.txt` in the receipt directory.

### Annabelle correction before attempt 8

Keep read isolation intact while making a denied read recoverable: introduce a distinct read-scope denial tool error that returns no file content, records a bounded denial in execution history, and asks Brenda to proceed using only authorized paths. Continue terminating immediately for out-of-scope writes, path escapes, unauthorized proof commands, and other scope violations. Add runner tests proving the model can continue after a denied read and tests proving unauthorized writes still stop. Preserve this attempt's receipts, then remove its disposable worktree and branch before the fresh rerun.

The denied-read correction is committed in `brenda_the_builder` as `031eb4a` (`Recover from denied out-of-scope reads`). Unauthorized read requests now return a no-content denial, are receipted as `read_scope_denied`, and give bounded feedback so Brenda can continue. Unauthorized writes and other hard scope violations still stop the run. The Brenda suite passed **30 tests**; `git diff --check` passed. Attempt 7's failed worktree and branch were removed only after its receipts and independent Sandy proof were preserved. A fresh attempt 8 will use the same pinned D&D baseline and unchanged Penny unit.

### Attempt 8 launch setup failure

A first launch after commit `031eb4a` created a fresh baseline worktree but failed before preflight or any model call: Brenda's default receipt root `/Users/evertj/.local/state/brenda` is outside this helper's writable root. The traceback is recorded in the Hanna session output; no run receipts existed and the worktree had no candidate edits. That provisional worktree/branch was removed. The next launch explicitly points `BRENDA_STATE_ROOT` at the authorized Hanna receipt directory and uses the work-farm `.brenda-worktrees` path.

## Attempt 8: model response exceeded the client timeout

The authorized-root launch used a new worktree for the same fixed unit and baseline:

- **Run ID:** `20260928T115610Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260928T115610Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260928T115610Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260928T115610Z-dnd-p001-show-ring-to-mira/`

Bootstrap verified the expected model before the first call. Brenda first denied its pre-write read of `dnd_combat/intent.py`, then wrote that authorized file. A later model call timed out at the current 180-second client limit. `ensure-running 35b` verified/recovered the owned local service and Brenda retried the same step; the retry progressed through the full 17,758-token source context, but again exceeded the 180-second limit before returning an action. Brenda stopped with `ENVIRONMENT_FAILURE`. No out-of-scope paths were changed. Git status is preserved in `git-status.txt`; the only candidate path was `dnd_combat/intent.py`, copied to `candidate-intent.py`, and raw actions and transport recovery receipts remain available.

Sandy independently ran `python3 -m unittest discover -v` at `2026-09-28T12:06Z`; all **37 baseline tests passed**. The candidate does not connect its new resolver to the terminal or add acceptance tests, so Penny's requirement is not met. Sandy decision: **FAIL**. Output is preserved in `sandy-proof-independent.txt`.

### Annabelle correction before attempt 9

The retry did not fail due to endpoint startup or scope; MLX logs show the long authorized prompt processing continued past the 180-second urllib timeout. Raise Brenda's model-call timeout to a deterministic bounded 600 seconds and add a request test for that timeout. Keep the fixed Penny unit and context intact. Preserve the run, then use a fresh worktree from the same baseline.

The model-response timeout correction is committed locally in `brenda_the_builder` as `a2001ef` (`Allow long local model responses`). Brenda's model HTTP timeout is now a fixed bounded 600 seconds, with a request-level regression test. The full suite passed **30 tests**, and `git diff --check` passed. Attempt 8's evidence was preserved and its failed worktree and branch were removed. Attempt 9 will use the same baseline and unit in a fresh worktree.

## Attempt 9: generic read denial did not redirect Brenda

Brenda ran after the 600-second timeout correction, using a fresh worktree from the same D&D baseline and exact unit:

- **Run ID:** `20260928T120731Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260928T120731Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260928T120731Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260928T120731Z-dnd-p001-show-ring-to-mira/`

OptiQ readiness succeeded. All 16 model actions requested the unauthorized read `dnd_combat/commands.py`; Brenda received no file content, and the runner receipted each `read_scope_denied` while continuing within the step budget. Brenda never wrote a candidate file. Runner terminal: `FAILED`, `model_done: false`, summary `model step budget exhausted`. `final.json` confirms `changed_paths: []`, `scope_clean: true`, and the proof command exit code 0.

Sandy independently reran `python3 -m unittest discover -v`; all **37 baseline tests passed**. No candidate behavior was built; Sandy decision: **FAIL**. Independent output, raw model actions, denial events, runner proof, and clean Git status are preserved in the run receipt directory.

### Annabelle correction before attempt 10

The generic denial message did not redirect the model. Brenda's runner now includes the complete authorized `read_paths` list and explicitly says not to request the denied path again. This follow-up is committed as `12138f9` (`Make read denials explicit to Brenda`); the 30-test suite passed. The attempt 9 worktree and branch are being removed after preserving its evidence. Retry the same Penny unit and baseline in a new worktree using this correction.

## Attempt 10: implementation created, exact-candidate contract failed

Brenda ran the same unit and baseline in a fresh worktree after commits `a2001ef` and `12138f9`:

- **Run ID:** `20260928T122919Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260928T122919Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260928T122919Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260928T122919Z-dnd-p001-show-ring-to-mira/`

Preflight verified the expected OptiQ model. Brenda denied an unauthorized `commands.py` read and then wrote only authorized paths: `dnd_combat/intent.py`, `dnd_combat/__main__.py`, and `tests/test_intent.py`. It used 16 model steps, repeatedly revised `__main__.py`, wrote its intent tests at step 15, and read the authorized main file at step 16. Brenda did not issue `done`; runner terminal was `FAILED` with `model_done: false`. The exact proof command ran 49 tests and failed one test.

Sandy independently reran the exact proof at `2026-09-28T13:35Z`: **49 tests, one failure**. `test_extra_words_around_candidate_are_rejected` expected `resolve_intent('please show the ring to Mira')` to return `None`; it returned `'talk'`. The implementation also accepts multiple unsupported phrasings and pronouns despite Penny specifying only one fixed candidate. **Sandy decision: FAIL.** Independent test output, full model actions, runner proof, candidate files, diff, and Git status are preserved in the receipt directory.

### Annabelle correction before attempt 11

The earlier bounded progress context included latest content only for write paths that were not also read paths. Brenda repeatedly rewrote `dnd_combat/__main__.py`, which Penny authorizes for both reading and writing, without receiving its latest generated contents in the ledger. Preserve bounded latest content for every path Brenda writes, including read/write paths, while retaining full actions in receipts. Add a runner regression test proving that the next model request receives the current contents of a read/write target after Brenda writes it. Keep existing context limits. The 30-test Brenda suite must pass; then remove this failed worktree and retry the unchanged unit from the same baseline.

The read/write-path progress-context correction is committed locally in Brenda as `807e8b0` (`Share latest edits for read-write paths`). Brenda now records the latest successful content for every written path, including `__main__.py` which Penny authorizes for both reading and writing; the execution ledger presents it under the existing 7,000-character cap and keeps full content in receipts. A new runner test covers follow-up context for a path that is both readable and writable. The complete Brenda suite passed **31 tests**, and `git diff --check` passed. Attempt 10's candidate, failing proof, Sandy result, action receipts, and status/diff evidence are preserved; its disposable worktree and branch are removed.

## Attempt 11: resolver created, gallery restriction and acceptance tests missing

Brenda ran the same unit and baseline in a fresh worktree with commit `807e8b0`:

- **Run ID:** `20260928T133750Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260928T133750Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260928T133750Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260928T133750Z-dnd-p001-show-ring-to-mira/`

Bootstrap verified expected OptiQ before step 1. Brenda changed only `dnd_combat/intent.py` and `dnd_combat/__main__.py`, within Penny's write scope. It used all 16 steps without a `done` action. The proof command passed all **37 baseline tests**, but Brenda added no acceptance tests. Sandy independently reran the same command and got the same 37 passing baseline tests.

Sandy inspected the final resolver and terminal integration. The resolver matches the single phrase `I show the ring to Mira`, and `execute_intent` routes it through `game.talk('Mira')`. However, the terminal calls `resolve_intent(raw_choice)` from the general unrecognized-input `else` branch with no current-room/gallery guard. Thus it can execute in rooms beyond the gallery, contrary to Penny. No candidate test exercises the terminal integration or gallery restriction. **Sandy decision: FAIL.** Independent proof, complete raw actions, candidate snapshots, diff and Git status are preserved in the receipt directory.

### Annabelle correction before attempt 12

Even after Brenda could see its latest generated files, it spent steps 5–15 repeatedly revising only `intent.py`, leaving other authorized acceptance-test paths untouched and not enforcing the gallery-only route. Add deterministic runner feedback after each successful write that lists Penny's write paths still untouched in the worktree. Keep all paths within Penny's fixed write scope and retain current full-action receipts and context bounds. Add tests for this remaining-path feedback. Run the Brenda suite, commit locally, remove this failed worktree, and rerun the same unit from the same D&D baseline.

The untouched-path feedback correction is committed in Brenda as `ed2569c` (`Surface untouched authorized work paths`). After each successful write, Brenda now receives the list of Penny-authorized write paths not yet changed, qualified as awareness only and usable only if needed for the goal; once each has been touched, the ledger records that fact. Brenda's full suite passed **32 tests**, including a regression test for the pending-path list and its cleared state. Attempt 11's evidence is preserved and its worktree/branch are removed. Attempt 12 uses the same D&D baseline and unit in a new worktree.

## Attempt 12: remaining-path feedback did not shift implementation work

Brenda ran after commit `ed2569c` in a new worktree from the exact same unit and baseline:

- **Run ID:** `20260928T210533Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260928T210533Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260928T210533Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260928T210533Z-dnd-p001-show-ring-to-mira/`

Bootstrap verified OptiQ. Brenda wrote `dnd_combat/intent.py` at steps 3 and 5–16, and `dnd_combat/__main__.py` once at step 4. It did not touch any test path or issue `done`; terminal state `FAILED`, summary `model step budget exhausted`. The Penny proof passed all **37 unchanged baseline tests**; Sandy independently reran it and got the same result.

Sandy's review found the resolver accepts several unsupported phrasings (including pronoun and archivist variants) rather than only the fixed candidate. `__main__.py` invokes `resolve_intent(raw_choice)` in the general unrecognized-input branch, with no gallery-room check, so the behavior is not restricted to the gallery. No acceptance tests were added. **Sandy decision: FAIL.** Receipts preserve all model revisions, the two candidate files, proof output, independent proof, diff, and Git status.

### Annabelle correction before attempt 13

Attempt 12 shows a plain remaining-path list is too passive: Brenda kept revising the resolver. Update the runner's progress message to sort untouched test paths first and explicitly direct Brenda to take the next action from an untouched test path before revising already changed files, while allowing an implementation revision when required by proof or the unit goal. Keep all paths Penny-authorized and preserve context limits. Add a runner test for test-path-first ordering and wording. Run Brenda tests, commit, remove this worktree, and retry the same unit at the pinned baseline.

The test-path prioritization correction is committed in Brenda as `71b61ce` (`Prioritize untouched Penny test paths`). Runner feedback now lists test paths before other outstanding write paths and directs Brenda to use an untouched test path before revising an already changed file, unless proof or the unit goal requires that revision. A runner test verifies both the ordering and wording. Brenda's suite passed **32 tests** and `git diff --check` passed. Attempt 12's evidence is preserved; its failed worktree and branch are removed. Attempt 13 will use a fresh worktree at the same pinned baseline and unchanged unit.

## Attempt 13: model OOM interrupted before the bounded unit completed

Brenda ran the unchanged Penny unit from the pinned baseline in a new worktree after commit `71b61ce`:

- **Run ID:** `20260928T215025Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260928T215025Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260928T215025Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260928T215025Z-dnd-p001-show-ring-to-mira/`

Preflight verified the expected OptiQ model. Brenda wrote `dnd_combat/intent.py` and `tests/test_intent.py`, then the next model call failed after MLX logged a Metal `Insufficient Memory` error while evaluating an 18,546-token prompt. The server continued answering `/v1/models`, so the then-current transport recovery treated it as ready; that retry ended with a closed connection. Brenda terminated with `ENVIRONMENT_FAILURE` before issuing `done` or running its proof. Sandy's independent exact proof ran 42 tests and failed one: `test_missing_keyword_is_rejected` asserts that the exact accepted phrase is rejected. The candidate also has no terminal integration or gallery-only guard. **Sandy decision: FAIL.** Raw actions, candidate snapshots, independent proof, final event, and Git status/diff evidence are preserved in the receipt directory.

### Durable process corrections after attempt 13

The attempt showed that `ensure-running` returned early for a healthy-looking orphan after the Screen session had vanished. In mlx_server, commit `3adca81` makes recovery identify the listener even when `/v1/models` responds, re-verifies the same PID and full checkout/runtime ownership immediately before SIGTERM, and refuses changed, ambiguous, foreign, or non-loopback listeners. Tests cover the owned signal case and no-signal refusal cases. Recovery of the verified owned PID `33626` restarted `35b` offline and verified the advertised OptiQ model. Commit `7a21ebe` adds a `recover 35b` path that stops only the named managed Screen session, then delegates orphan handling to the ownership-checked `ensure-running` flow.

In Brenda, commit `ee1e953` caps preloaded authorized source context at 32,000 characters while retaining exact full source receipts, and uses the new local `recover 35b` path after transport failures. This addresses the 88 KB of source that had been replayed into every model prompt and the healthy-endpoint check after generation OOM. Brenda's full suite passed 24 tests; mlx_server's suite passed 9 tests, `bash -n scripts/mlx-server`, `py_compile`, status, and diff checks passed. No D&D unit or implementation was changed.

The failed worktree and branch for attempt 13 are removed after preserving the evidence above. Continue with the identical unit and baseline in a fresh worktree.

## Attempt 14: context fix worked; replacement-test churn blocked acceptance

Brenda ran after local commits `3adca81`/`7a21ebe` in mlx_server and `ee1e953` in Brenda:

- **Run ID:** `20260928T234455Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260928T234455Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260928T234455Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260928T234455Z-dnd-p001-show-ring-to-mira/`

The new 32,000-character preloaded-source cap reduced the first full MLX prompt to about 8,395 tokens; later prompts stayed near 11,100 tokens, and the prior Metal OOM did not recur. Brenda wrote all five Penny-authorized paths, including terminal integration and three test files, but repeatedly rewrote only `dnd_combat/intent.py` after the first proof. The final `intent.py` exports `match_intent`, while the terminal and new tests import `interpret_intent`; it therefore fails to import. Brenda exhausted all 16 steps without `done`. Its final proof and Sandy's independent exact proof both ran 34 tests and failed with two import errors plus one narrator assertion failure. Replacing `tests/test_narrator.py` removed existing baseline assertions. The terminal change also has no explicit gallery-only guard. No out-of-scope files changed. **Sandy decision: FAIL.** Full actions, candidate snapshots, proof outputs, diff, and status are preserved in the receipt directory.

### Deterministic test-preservation correction before attempt 15

Attempt 14 repeatedly replaced existing test files and dropped their baseline tests, then changed the implementation API away from the API imported by its own test and terminal files. Add a deterministic `write_file` guard for existing authorized test files: a new version must retain every baseline `test_*` function name; otherwise reject that write with the missing names and an instruction to preserve the existing tests while adding or updating relevant cases. Add tests proving rejected replacement leaves the file unchanged and a version that retains baseline tests succeeds. This keeps the recovery in the runner/tooling and leaves Penny's unit fixed. After the Brenda suite passes, remove attempt 14's disposable worktree and retry from the same baseline.

## Attempt 15: test baseline was preserved; MLX OOM recovery hit Screen permissions

Brenda ran after commits `dc842f8` and `4791090` in a new worktree:

- **Run ID:** `20260929T001305Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260929T001305Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260929T001305Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260929T001305Z-dnd-p001-show-ring-to-mira/`

Preflight passed and Brenda wrote only `dnd_combat/intent.py` and `tests/test_intent.py`. The model then hit Metal out-of-memory. The new `recover 35b` flow stopped the named Screen session and found no listener, but its sandboxed Screen startup reported `Operation not permitted` for the local MLX executable. The run stopped as `ENVIRONMENT_FAILURE` before completion or proof. The same repository `ensure-running 35b` command was then run with authorized process-control escalation; its managed Screen session and `/v1/models` OptiQ advertisement were verified and receipted. Sandy's independent exact proof found 47 tests with one new test failure: `test_non_string_proposal_ignored`. The candidate also lacks terminal integration and gallery-only enforcement. **Sandy decision: FAIL.** Receipts preserve model actions, the recovery error, subsequent readiness proof, candidate files, and independent test output.

### Durable corrections after attempt 15

Brenda commit `4791090` reduces preloaded source from 32,000 to 16,000 characters and keeps latest generated-file context/ledger smaller. After a recover command exits nonzero, Brenda now checks that the named managed Screen session is up and `/v1/models` advertises the expected OptiQ model before treating recovery as ready; it preserves the error output regardless. Brenda's test suite passed 25 `unittest` tests and 35 pytest tests. This is intended to handle a Screen wrapper error after the local service has actually become ready. The exact Penny unit remains unchanged.

Attempt 15's worktree and branch are removed after preserving the receipts. Rerun from a new worktree at the same baseline and exact unit.

## Attempt 16: deterministic test ordering is needed

Brenda ran after commit `4791090` in a fresh worktree:

- **Run ID:** `20260929T003657Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260929T003657Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260929T003657Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260929T003657Z-dnd-p001-show-ring-to-mira/`

OptiQ preflight passed; prompts were smaller and no OOM occurred. Brenda wrote `intent.py`, `__main__.py`, and `tests/test_intent.py`, then repeatedly rewrote only `tests/test_intent.py` and `intent.py` through all 16 steps. It did not touch the other two authorized test paths and did not issue `done`. The final implementation exports `resolve_talk_intent`, but the terminal imports `resolve_intent`; `tests/test_intent.py` also imports `resolve_intent`. Sandy's independent exact proof failed with two import errors in 34 tests. **Sandy decision: FAIL.** All raw actions, candidate snapshots, proof outputs, diff, and status are preserved in the receipt directory.

### Deterministic correction before attempt 17

Untouched-test-path ordering and baseline-name preservation were insufficient because Brenda repeatedly rewrote newly created `tests/test_intent.py`. Add a tool guard that rejects rewriting any successfully written authorized path while another Penny-authorized test path is still untouched. The denial must list those paths, so the next step can establish each test path before changing previous files. Cover the guard with tests; retain the separate check that existing baseline test names cannot be removed. Then remove attempt 16's disposable worktree and retry.

The attempt-17 correction is committed locally in Brenda as `7d634a1` (`Require untouched tests before rewriting authorized files`). `write_file` now denies rewrites of any already-written authorized path while test paths remain untouched, naming the required test paths; the baseline test-name guard remains in force. Pytest passed 36 tests and unittest discovery passed 25 tests. Attempt 16's worktree/branch have been deleted after preserving its evidence.

## Attempt 17: transport recovery was blocked by sandboxed Screen startup

Brenda ran after commit `7d634a1` from a fresh worktree:

- **Run ID:** `20260929T005519Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260929T005519Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260929T005519Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260929T005519Z-dnd-p001-show-ring-to-mira/`

Preflight verified OptiQ. Brenda wrote `intent.py` and `__main__.py`; its next response was malformed JSON, and the same-step retry later ended with a closed connection. The runner's `recover 35b` path ran, but sandboxed Screen could not execute `mlx_lm.server`; the managed-session status then exited 1, so Brenda stopped as `ENVIRONMENT_FAILURE`. Using authorized escalation, `recover 35b` stopped the named session, verified orphan PID `49199` belonged to the local mlx_server checkout/runtime, sent SIGTERM, started the offline 35B profile, and verified the expected `/v1/models` model. The startup and endpoint receipts are preserved in the run directory. Sandy's independent exact proof had one import error in 33 tests; the candidate also lacks the acceptance test paths and does not issue `done`. **Sandy decision: FAIL.** Candidate files, complete model receipts, failure proof, diff, and status are saved.

Attempt 17's failed worktree and branch are removed after preserving evidence. Continue from the same exact unit and baseline; the deterministic test-path rewrite guard is committed and validated.

## Attempt 18: duplicate authorized reads consumed the remaining steps

Brenda ran after commit `7d634a1` in another fresh worktree:

- **Run ID:** `20260929T011119Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260929T011119Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260929T011119Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260929T011119Z-dnd-p001-show-ring-to-mira/`

OptiQ preflight passed. Brenda wrote `dnd_combat/intent.py` and `tests/test_intent.py`, then used the remaining steps rereading the already preloaded, unchanged `dnd_combat/__main__.py`. It issued no `done`. The final proof and Sandy's independent proof failed with one import error in 38 tests. **Sandy decision: FAIL.** All raw actions, candidate files, proof, diff, and status are preserved.

### Deterministic correction before attempt 19

Attempts 17 and 18 show repeated reads of unchanged, already-preloaded paths consume action steps without changing the context. Permit one explicit full read of an authorized preloaded file, then reject further reads of that unchanged path with clear next-action feedback. Continue to allow reads of a path after Brenda has written it, so it can inspect its current generated content. Add tests for both cases, run the Brenda suites, remove attempt 18's failed worktree, and retry the unchanged unit.

Attempt-19 correction is committed in Brenda as `cacac7c` (`Limit redundant reads of preloaded Brenda sources`). Preloaded files may be reread once to return their full contents; another unchanged repeat is denied with next-action feedback. Reads after Brenda writes a path still return its current contents. Tests cover the one-reread limit and post-write access. Brenda's suites passed 37 pytest tests and 25 unittest tests. Attempt 18's failed worktree and branch are removed after preserving evidence.

## Attempt 19: test-preservation guard worked; model responses exhausted the budget

Brenda ran after commit `cacac7c` in a fresh worktree:

- **Run ID:** `20260929T011708Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260929T011708Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260929T011708Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260929T011708Z-dnd-p001-show-ring-to-mira/`

OptiQ preflight passed with no OOM. Brenda wrote `intent.py`, `tests/test_intent.py`, and `__main__.py`. A proposed replacement of `tests/test_terminal_smoke.py` was rejected because it removed baseline test names, and the original file remained intact. Brenda reread that authorized source file but then generated five malformed JSON actions and exhausted the 16-step budget without writing terminal-test coverage or issuing `done`. The exact proof and Sandy's independent proof failed with one import error in 33 tests. **Sandy decision: FAIL.** Full actions, protocol-error responses, candidate snapshots, proof, diff, and status are preserved.

### Deterministic correction before attempt 20

The test-preservation denial should direct Brenda to `read_file` the authorized existing test file before retrying the write, giving it the full exact contents rather than just missing test names. Also deny duplicate model reads when a path has not changed since its previous model read; after a successful write, allow one read of the updated content. Add tests for both rules, remove attempt 19's disposable worktree, and retry unchanged Penny scope/baseline.

Attempt-20 correction is committed locally in Brenda as `e489af8` (`Give actionable feedback for protected test rewrites`). A rejected baseline-test replacement now explicitly directs Brenda to read the complete authorized file before editing it; unchanged content can be read once per version, with one fresh read available after each successful write. Tests verify feedback and the read lifecycle. Pytest passed 37 tests; unittest discovery passed 25 tests. Attempt 19's worktree and branch are removed after preserving its evidence.

## Attempt 20: baseline proof stayed green, but Brenda did not finish the feature

Brenda ran after commit `e489af8` in a fresh worktree:

- **Run ID:** `20260929T015358Z-dnd-p001-show-ring-to-mira`
- **Branch:** `brenda/20260929T015358Z-dnd-p001-show-ring-to-mira`
- **Worktree:** `/Users/evertj/git/.brenda-worktrees/DnD_Bot_Interface/20260929T015358Z-dnd-p001-show-ring-to-mira`
- **Baseline:** `a7d2760045a46f6b992535a9141ed3a8f74596d9`
- **Unit SHA-256:** `f8affcff72cecfac3e5947fab7b5541cd334115a941898f0765b326e60cc42d0`
- **Receipts:** `/Users/evertj/.local/state/foreman-interface/hanna/brenda-receipts/20260929T015358Z-dnd-p001-show-ring-to-mira/`

OptiQ preflight and the 37-test baseline proof passed. Brenda wrote `intent.py` and `tests/test_intent.py`. A replacement for `tests/test_narrator.py` was correctly rejected; Brenda used the next action to read its full authorized source. It then spent the rest of the run rereading unchanged `__main__.py`, which was rejected after the first reread. It did not write terminal integration or the gallery-specific smoke test and did not issue `done`. A green baseline is not feature evidence. **Sandy decision: FAIL.** All receipts, candidate files, proof, diff, and status are preserved.

### Deterministic correction before attempt 21

Duplicate-read denials must explicitly name untouched authorized test paths and direct Brenda to write one before revisiting already written implementation paths. Keep the bounded read behavior, but make feedback actionable and test it. Remove attempt 20's worktree and retry from the same exact baseline/unit.

Attempt-21 correction is committed as `96d5d67` (`Prioritize untouched tests after duplicate reads`). A repeated-read denial now names authorized test paths still untouched and directs Brenda to write one before rereading the unchanged source. The regression test covers that message. Pytest passed 37 tests and unittest discovery passed 25 tests. Attempt 20's worktree/branch have been removed with evidence preserved.
