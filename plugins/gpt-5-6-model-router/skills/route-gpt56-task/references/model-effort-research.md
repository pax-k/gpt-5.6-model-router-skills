# GPT-5.6 model and effort decision

Status: accepted for router v0.4.1
Decision date: 2026-07-24

## Evidence

OpenAI currently describes:

- GPT-5.6 Sol as the frontier model for complex professional work;
- GPT-5.6 Terra as the balance of intelligence and cost;
- GPT-5.6 Luna as the efficient option for cost-sensitive, high-volume work.

All three support `none`, `low`, `medium`, `high`, `xhigh`, and `max`.
OpenAI recommends `medium` as the balanced starting point, `low` for
latency-sensitive workloads, `high` or `xhigh` only when representative
evaluation shows a quality gain, and `max` only for the hardest quality-first
workloads. For tool-using workflows, `none` should be compared with `low`.

Canonical sources:

- https://developers.openai.com/api/docs/guides/latest-model#update-api-and-model-parameters
- https://developers.openai.com/api/docs/models/gpt-5.6-sol
- https://developers.openai.com/api/docs/models/gpt-5.6-terra
- https://developers.openai.com/api/docs/models/gpt-5.6-luna
- https://learn.chatgpt.com/docs/codex/codex-manual#choosing-models-and-reasoning

Published guidance does not establish a complete dominance order between every
model/effort pair. Cross-family choices below are governed-router policy and
must be evaluated on representative routed work.

## Selection axes

Choose the model family from the task's ambiguity, required judgment, and risk:

- Luna: clear, repeatable, low-risk work with objective verification.
- Terra: bounded work requiring normal engineering judgment or broad
  evidence-gathering.
- Sol: ambiguous, architectural, cross-layer, failed, or critical work.

Choose effort independently from the exploration and verification burden:

- `medium`: normal repository reasoning and tool use.
- `high`: strongly verified mechanical work, competing hypotheses, complex
  logic, edge cases, difficult debugging, or independent critical review.

The v0.4.1 custom-agent catalog does not expose low, xhigh, or max. Recorded
failure is absorbed by replanning at the next retained route, with Sol/high as
the ceiling.

Context breadth alone does not select Sol. A large read-only search can remain
Terra/high; Sol is selected when synthesizing the evidence requires frontier
judgment or the risk floor requires it.

## Curated route frontier

| Combination | v0.4.1 treatment | Intended use |
| --- | --- | --- |
| Luna/none | Do not expose as a custom agent | Deterministic or latency-baseline work belongs at root or in scripts |
| Luna/low and medium | Do not expose | The retained Luna worker uses high verification effort |
| Luna/high | Keep | Narrow mechanical work with objective acceptance and strong verification |
| Luna/xhigh and max | Do not expose | Replan with Terra or Sol instead of increasing Luna effort |
| Terra/none | Do not expose | Routed repository work normally benefits from reasoning and tools |
| Terra/low | Experimental only | Candidate for fast scouting after evaluation |
| Terra/medium | Keep | Everyday implementation and read-heavy exploration |
| Terra/high | Keep narrowly | Broad evidence-led investigation with competing hypotheses |
| Terra/xhigh and max | Do not expose | Escalate to Sol |
| Sol/none and low | Do not expose | Sol and the critical floor imply a non-trivial reasoning requirement |
| Sol/medium | Keep | Architecture, ambiguity, cross-layer or critical implementation, advice |
| Sol/high | Keep | Difficult work, debugging, quality-first execution, and independent critical review |
| Sol/xhigh and max | Do not expose | Replan at the Sol/high ceiling |

“Do not expose” means the router does not bundle or recommend a custom role for
that pair. It does not claim the API combination is invalid.

## v0.4.1 role decision

Retain eight roles and five model/effort combinations.

- Luna/high worker
- Terra/medium explorer and worker
- Terra/high investigator
- Sol/medium engineer and advisor
- Sol/high debugger and reviewer

The former Sol/xhigh and Sol/max specialist responsibilities are absorbed into
the Sol/high debugger. A recorded Sol/high failure requires a materially revised
plan, narrower decomposition, or stronger verifier evidence before retrying.

The Terra/high investigator is valid only for broad evidence surfaces with
competing hypotheses. Architectural ambiguity, criticality, or weakly verified
critical risk selects Sol instead.

## Evaluation

Use sanitized representative tasks and compare adjacent candidates:

1. Luna/high versus Terra/medium.
2. Terra/medium versus Terra/high.
3. Terra/high versus Sol/medium.
4. Sol/medium versus Sol/high.

Record task acceptance, verifier pass rate, independent-review findings,
unsupported assumptions, retries, latency, input/output/reasoning tokens, and
effective cost. Retain only pairs that occupy a useful quality, latency, or
cost region. A cheaper first attempt is not a saving when retries make the
complete task more expensive.
