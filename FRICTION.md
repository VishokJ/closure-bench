# closure-bench: friction log

The most important problems we hit with `verifiers`, Prime Lab and the toolchain, most costly first. The common thread: several platform failures turn silently into reward 0. That biases evaluation means, and would bias RL batches.

## 1. Provider errors become reward 0

- **What happened.** Prime Inference intermittently returned 502s and streams that ended early ("upstream stream ended before its terminal event"). With the default `retries.max_retries = 0`, each one ended the rollout with reward 0. In the mean reward, these look exactly like model failures. We found them only by reading `stop_condition` in the traces; 3 of 26 rollouts in one Qwen sanity run were lost this way.
- **Recommendation.**
  - Ship a default retry rule for provider errors (`ProviderError`, 5xx, interrupted streams): a few attempts with backoff.
  - When retries run out, mark the rollout as an infrastructure failure that is left out of reward means and training batches, never reward 0.
  - Print the infrastructure count next to the mean, and warn when any errored rollout is inside the mean.

## 2. Truncated and timed-out runs are scored like ordinary failures

- **What happened.** A model that spends its whole token budget thinking, or hits the agent timeout, submits nothing and scores 0, the same as a wrong answer. 10 of 52 Nemotron attempts in one probe were truncations we first read as syntax errors. Telling them apart took digging through token counts.
- **Recommendation.**
  - Report the stop reason distribution (truncated, timed out, completed) in every eval summary by default.
  - Make the scoring choice explicit at configuration time: score these runs as 0, or skip them. A silent default hides a capacity limit as a capability gap.
  - For training, default to keeping truncated runs out of the batch unless the environment opts in.

## 3. Provider responses outside the OpenAI schema

- **What happened.** Prime Inference occasionally returned `finish_reason: "error"`, which isn't an OpenAI value. The client's response parser rejected it (`validation error for ModdedChatCompletion`), and the rollout ended as a provider error.
- **Recommendation.**
  - Normalize responses at the Prime Inference boundary: return an HTTP error instead of an in-band `"error"` finish reason.
  - Have the client treat unknown finish reasons as retryable provider errors, not parse failures.
  - Document every Prime-specific field.

## 4. Sandbox creation failures look like task failures

- **What happened.** Our task-generation gates run in Prime sandboxes through our own executor on the `prime-sandboxes` SDK. Under parallel load, sandbox creation and image loading occasionally timed out. Some of this is likely our own executor, not the platform. But the SDK gave no way to tell "could not start" from "the work failed", so we built our own rule: retry once, then stop the run, and never let a sandbox failure reject a candidate task.
- **Recommendation.**
  - In the `prime-sandboxes` SDK, queue creation requests instead of failing them under load.
  - Raise a distinct, retryable error type for creation and load failures.
  - Publish the concurrency limits per account.

## 5. Answers left inside the reasoning

- **What happened.** In 4 Qwen attempts the response ended normally (`finish_reason: "stop"`) with empty content. A complete testbench sat only in the reasoning text. We could not tell whether the model or the serving layer caused it, and the attempt scored 0.
- **Recommendation.**
  - Flag "empty content after reasoning" as its own stop condition.
  - Offer an opt-in harness setting that extracts the final answer from the reasoning when the content is empty.

## 6. Toolchain: Verilator and formal tools

- **What happened.**
  - **Verilator crashed** with an internal error on 2 Qwen testbenches, and those scored as the model's compile errors.
  - **A redefined module silently kept its first definition.** Verilator only warns about duplicates, and the `-Wno-fatal` flag needed for model-written code made that warning non-fatal.
  - **Our early formal "timeouts" were mostly witness minimization,** about 820 of 900 s.
- **Recommendation.**
  - **For verification environments on Prime:** classify simulator internal errors as infrastructure, not model failures; make security-relevant warnings (duplicate modules) fatal even when other warnings are not; give witness minimization a budget separate from the search.
  - **For the eval images:** pin and publish the simulator version.

## 7. Token and time limits interact silently

- **What happened.** With `max_tokens = 65536` and `agent_timeout = 900`, Qwen (about 70 tokens/s) hit the timeout long before the token limit: 6 of 26 attempts in one run. Each limit was reasonable alone; together they capped reasoning without any warning. This one is mostly our configuration mistake, but it is easy to make and the tooling could catch it.
- **Recommendation.**
  - Validate configurations at launch: estimate the time `max_tokens` needs from the model's measured throughput, and warn when the agent timeout is shorter.
  - Record which limit ended each rollout as its own stop condition.
