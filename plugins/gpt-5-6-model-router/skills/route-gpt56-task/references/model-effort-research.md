# GPT-5.6 model and effort research

Status: Implemented calibration reference, current through 2026-07-19. The
v0.2 policy uses this evidence for its default ladder and escalation gates.
It does not make every API-supported model/effort pair a production default;
`SKILL.md`, structured route decisions, schema-2 TOMLs, and tests remain the
runtime authority.

## Contents

- [Documented model positioning](#documented-model-positioning)
- [Cost and capability surface](#cost-and-capability-surface)
- [Benchmark evidence](#benchmark-evidence)
- [Reasoning effort](#reasoning-effort)
- [Operational interpretation](#operational-interpretation)
- [Evidence limitations](#evidence-limitations)
- [Sources](#sources)

## Documented model positioning

OpenAI positions the GPT-5.6 family as follows:

- `gpt-5.6-sol`: flagship capability for complex professional work.
- `gpt-5.6-terra`: balance of intelligence, speed, and cost; the everyday
  workhorse.
- `gpt-5.6-luna`: lowest-cost and lowest-latency family member for clear,
  repeatable, high-volume work.
- The `gpt-5.6` API alias routes to `gpt-5.6-sol`.

OpenAI's Codex guidance describes Sol as suitable for ambiguous, multi-step work
requiring planning, tool use, validation, and broad-context follow-through. It
describes Terra as suitable for exploration, read-heavy scans, large-file
review, and supporting-document processing. It describes Luna as suitable for
extraction, classification, transformation, and structured summaries with a
known quality bar.

## Cost and capability surface

Standard API token prices per one million tokens:

| Model | Input | Cached input | Output |
| --- | ---: | ---: | ---: |
| Luna | $1.00 | $0.10 | $6.00 |
| Terra | $2.50 | $0.25 | $15.00 |
| Sol | $5.00 | $0.50 | $30.00 |

All three model pages document:

- 1,050,000-token context window.
- 128,000 maximum output tokens.
- Text and image input; text output.
- Reasoning-token support.
- Responses API, Chat Completions, Batch, streaming, structured output,
  function calling, file search, web search, prompt caching, and the same broad
  hosted-tool surface.

Do not route by nominal tool availability or context-window size alone. The
published window is the same, while measured ability to use very long context
differs materially.

Prompts above 272K input tokens are billed at twice the input price and 1.5
times the output price for the full request. Cache writes cost 1.25 times the
uncached input rate. Reasoning tokens are output tokens and therefore affect
latency, context consumption, and cost.

## Benchmark evidence

OpenAI's launch evaluations show that tier gaps depend strongly on task shape:

| Evaluation | Sol | Terra | Luna | Interpretation |
| --- | ---: | ---: | ---: | --- |
| SWE-Bench Pro | 64.6% | 63.4% | 62.7% | Small tier gap on this coding harness |
| DeepSWE v1.1 | 72.7% | 69.6% | 67.2% | Sol leads; all remain competitive |
| Terminal-Bench 2.1 | 88.8% | 87.4% | 84.7% | Terra stays close to Sol |
| Internal Research Debugging | 68.3% | 67.8% | 50.8% | Luna drops on difficult diagnosis |
| SEC-Bench Pro | 71.2% | 57.7% | 48.9% | Large gap on complex security work |
| OpenAI MRCR 256K-512K | 91.5% | 89.6% | 41.3% | Luna is unsuitable as a default for huge-context recall |
| OSWorld 2.0 | 62.6% | 50.2% | 45.6% | Sol leads on difficult computer use |
| GeneBench Pro | 28.7% | 23.3% | 10.8% | Hard scientific work separates tiers |

GeneBench-Pro reports reasoning-level results for difficult multistage genomic
analysis. At each model's best mainline setting, Luna, Terra, and Sol reached
16.5%, 23.3%, and 28.7%. Sol increased from 3.7% at `none` to 14.4% at `low`,
22.5% at `medium`, 24.4% at `high`, 26.8% at `xhigh`, and 28.7% at `max`.
This shows that effort can materially improve difficult work, but gains diminish
and resource use rises.

Artificial Analysis reports Sol/Terra/Luna scores of approximately 59/55/51 on
its Intelligence Index and 80/77/75 on its Coding Agent Index at `max`. Its
intelligence-versus-cost frontier contains Luna and Sol configurations ahead of
Terra: for each tested Terra effort, it found a Luna or Sol configuration with
equal or better cost-adjusted intelligence. Treat this as harness-specific, not
as proof that Terra lacks operational value. Terra's lower latency and strong
repository performance still make it a useful everyday agent.

Early practitioner reports are inconsistent. Common observations include:

- Luna succeeds on mechanical edits when acceptance is objective.
- Terra works well for repository exploration and ordinary implementation.
- Sol is more reliable for planning, broad synthesis, and review, but can
  overbuild when scope constraints are weak.
- High, max, and multi-agent modes can burn quota without improving completion
  when the task boundary or verifier is poor.
- More expensive models do not compensate for missing source-of-truth tracing
  or inadequate regression checks.

Treat community reports as hypotheses for local evaluation, not policy proof.

## Reasoning effort

The GPT-5.6 API supports `none`, `low`, `medium`, `high`, `xhigh`, and `max`.
Standard and pro modes default to `medium` when effort is omitted. Individual
Codex surfaces may expose a narrower set; use only values in the current
callable schema.

Interpret effort independently from model tier:

- `none`: exact extraction, transformation, or classification with a
  deterministic validator; not a default for agentic work.
- `low`: one clear path, shallow tool loop, strong verifier, and latency
  sensitivity.
- `medium`: multiple steps, local tradeoffs, repository navigation, and normal
  implementation.
- `high`: difficult diagnosis, subtle compatibility or security reasoning,
  weak verification, or consequential decisions.
- `xhigh`: repeated high-effort failure, dense proof obligations, or a bounded
  problem where one missed interaction is expensive.
- `max`: rare quality-first frontier work after evaluation shows `xhigh` is
  insufficient or failure cost dominates usage.

`ultra` is not merely a higher single-agent effort. In Codex it uses subagents
for parallel work. OpenAI's launch evaluation used four agents, counted all
agent tokens in cost, and measured latency from the root agent. API pro mode is
also independent from reasoning effort and uses more model work to produce one
final answer.

Use the lowest effort that passes representative evaluations. When migrating
an existing workflow, OpenAI recommends testing the current effort and one
level lower rather than assuming the same or a higher setting is required.

## Operational interpretation

Use this default production ladder:

```text
Luna / low
  -> Terra / medium
  -> Sol / medium
  -> Sol / high
  -> Sol / xhigh or max only after evidence-backed escalation
```

Choose the model for intrinsic capability breadth, ambiguity, consequence, and
context use. Choose effort for how much search, comparison, hypothesis testing,
and verification the current unit of work requires.

Increase effort on the same model when the agent understands the domain and
tools but needs deeper search or checking. Increase model tier when failure
shows missing abstractions, instruction loss, inability to reconcile broad
context, repeated symptom-patching, new high-risk boundaries, or weak
verification with material impact.

Do not use Luna/max as an automatic substitute for Sol. Additional deliberation
does not guarantee stronger abstractions or broad-context judgment. Do not use
Sol/high for everything; doing so removes the cost and latency value of a
router and prevents meaningful evaluation.

## Evidence limitations

- OpenAI launch results are first-party evaluations and often use optimized
  harnesses, reasoning continuity, safeguards, or simulated latency.
- Some published evaluations do not expose raw runs or independent replication.
- Artificial Analysis supported OpenAI's prerelease evaluation, so treat it as
  external but not fully independent.
- One benchmark cannot determine the best route for a repository, tool set, or
  subscription-quota model.
- Requested reasoning levels do not guarantee fixed token use or latency.
- The correct deployment policy must be calibrated on representative tasks,
  end-to-end completion, required evidence, latency, tokens, cost, and rework.

## Sources

- [Using GPT-5.6](https://developers.openai.com/api/docs/guides/latest-model)
- [GPT-5.6 launch and evaluations](https://openai.com/index/gpt-5-6/)
- [GPT-5.6 Sol model](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
- [GPT-5.6 Terra model](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
- [GPT-5.6 Luna model](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
- [Reasoning models](https://developers.openai.com/api/docs/guides/reasoning)
- [Building agents](https://developers.openai.com/tracks/building-agents#how-to-choose)
- [Artificial Analysis GPT-5.6 evaluation](https://artificialanalysis.ai/articles/gpt-5-6-has-landed)
- [GeneBench-Pro](https://cdn.openai.com/pdf/21938268-21af-442f-af93-3b2249afb241/genebench-pro.pdf)
