# Proposed dynamic routing policy

Status: Implemented v0.2 routing policy. `route_task.py decide` evaluates its
structured task-profile contract; the schema-2 TOMLs and tests enforce the
role inventory. Advanced routes remain gated by this policy's escalation and
evidence requirements.

## Contents

- [Policy objective](#policy-objective)
- [Task profile](#task-profile)
- [Model selection](#model-selection)
- [Effort selection](#effort-selection)
- [Route matrix](#route-matrix)
- [Escalation](#escalation)
- [Risk and review](#risk-and-review)
- [Runtime permission enforcement](#runtime-permission-enforcement)
- [Parallelism](#parallelism)
- [Evaluation](#evaluation)

## Policy objective

Select the least expensive model and effort that satisfy task-specific quality,
consequence, verification, and runtime-enforcement requirements. Keep the root
model unchanged. Re-run routing whenever new evidence changes the task graph;
do not precompute a fixed agent tree at intake.

Separate model and effort decisions:

- Model tier answers how much capability breadth, abstraction, context use, and
  judgment the task requires.
- Effort answers how much search, deliberation, comparison, and checking the
  selected model should spend on the current unit.

## Task profile

Classify one bounded unit of work with these dimensions:

| Dimension | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| Ambiguity | Exact procedure | Minor local choices | Several plausible approaches | Requirements or architecture unresolved |
| Consequence | Cosmetic/read-only | Bounded internal effect | Public contract, persistent data, operational impact | Auth, secrets, payments, safety, destructive migration, critical logic |
| Context breadth | One artifact | Component/package | Several interacting subsystems | Cross-repository, distributed, organizational, or migration-wide |
| Irreversibility | Read-only | Trivial revert | Recovery needs coordination or data repair | Lossy, externally committed, or practically irreversible |
| Verification strength | No trustworthy oracle | Subjective/manual | Partial automated checks | Deterministic, broad, repeatable checks |
| Latency sensitivity | Offline/batch | Normal | Interactive | Hard deadline |

Also record:

- Primary kind: `mechanical`, `exploration`, `implementation`, `ambiguous`,
  `debugging`, or `review`.
- Current phase: intake, exploration, implementation, validation, repair, or
  review.
- Prior validation failures and their evidence.
- Read/write ownership and known file scopes.
- External, destructive, credentialed, or costly actions.
- Current agent depth and delegation budget.
- Required host/tool confirmations and explicit authority exclusions.

Risk, irreversibility, and weak verification are floors. Do not average them
away with several easy dimensions or a tight deadline.

## Model selection

### Luna eligibility

Use Luna only when all of these conditions hold:

- Ambiguity, consequence, breadth, and irreversibility are each 0 or 1.
- Verification strength is 2 or 3.
- The output shape or acceptance test is explicit.
- Failure is cheap to detect, retry, and reverse.

Typical tasks include formatting, extraction, classification, boilerplate,
bounded renames, repetitive edits, fixture generation, and deterministic data
transformation.

### Sol mandatory gates

Use Sol when any of these conditions holds:

- Ambiguity, consequence, or irreversibility is 3.
- Verification is 0 or 1 and an incorrect result has material impact.
- Broad context combines with architecture, migration, compatibility,
  concurrency, distributed state, security, or critical business logic.
- Debugging has survived one serious evidence-backed attempt.
- The work is independent review of a consequential change.
- A lower-tier agent repeatedly loses scope, instructions, or sources of truth.

### Terra default

Use Terra between Luna eligibility and Sol mandatory gates. Typical tasks
include repository exploration, ordinary implementation, bounded multi-file
changes, document synthesis, and work needing normal engineering judgment.

Terra is the everyday default; Luna is an earned optimization; Sol is an
ambiguity, consequence, or demonstrated-capability escalation.

## Effort selection

- Use `low` for one clear path, shallow tool use, strong verification, and
  latency-sensitive work.
- Use `medium` for several steps, local tradeoffs, repository navigation, and
  normal implementation.
- Use `high` for difficult diagnosis, subtle compatibility or security work,
  multiple sources or tradeoffs, weak verification, or consequential review.
- Use `xhigh` after high-effort failure, for dense proof obligations, or when a
  bounded task makes one missed interaction expensive.
- Use `max` only after a recorded `xhigh` failure, or when the human explicitly
  grants quality-first authority for the hardest bounded work. The latter is a
  deliberate cost/latency override and must be recorded in the decision.
- Use `none` only on surfaces that expose it and only for exact transformations
  or classifications with deterministic validation.

Use the lowest supported effort that meets the acceptance threshold.

## Route matrix

### Default production routes

| Task shape | Route | Role |
| --- | --- | --- |
| Clear, repeatable, low risk | Luna / low | Mechanical leaf worker |
| Read-heavy mapping and evidence gathering | Terra / medium | Read-only explorer |
| Everyday bounded implementation | Terra / medium | Worker |
| Ambiguous or architectural implementation | Sol / medium | Engineer |
| Difficult debugging or risky repair | Sol / high | Debugger |
| Independent consequential review | Sol / high | Reviewer |

### Gated advanced routes

| Route | Eligibility |
| --- | --- |
| Terra / high | Broad investigation or moderate debugging with competing hypotheses but no Sol gate |
| Sol / xhigh | A bounded task with improved evidence or verifier after a recorded Sol/high reasoning failure |
| Sol / max | A recorded Sol/xhigh failure, or explicit human quality-first authorization for the hardest bounded work |

Do not expose advanced routes as peers to the default ladder until evaluations
show repeatable value.

## Escalation

Escalate one dimension at a time when possible:

1. Increase effort on the same model when it understands the domain and tools
   but needs deeper search, comparison, or verification.
2. Increase model tier when failure shows missing abstractions, broad-context
   problems, repeated instruction loss, or inability to trace the source of
   truth.
3. Increase tier and effort together when new evidence reveals a Sol mandatory
   gate.
4. Add independent Sol/high review for consequential implementation even when
   a lower-tier primary remains appropriate.
5. Improve evidence, task boundary, or verification before moving Sol/high to
   Sol/xhigh or max.

Default validation-failure ladder:

```text
Luna / low -> Terra / medium -> Sol / medium -> Sol / high
```

Do not repeatedly rerun an identical model, effort, prompt, and evidence set.
That is retrying rather than escalation.

## Risk and review

Require automatic risk classification. Do not rely solely on a caller
remembering a `--consequential` flag.

Always require independent Sol/high review for changes involving:

- Authentication or authorization.
- Secrets or credentials.
- Payments or financial state.
- Personal or regulated data.
- Destructive or lossy migrations.
- Concurrency or distributed state.
- Public APIs, schemas, or compatibility guarantees.
- Safety boundaries or critical business logic.

Use Sol/high for the primary implementation when impact is severe,
irreversibility is high, verification is weak, or difficult security/state
reasoning is intrinsic. Otherwise, Terra/medium or Sol/medium may implement and
Sol/high must independently review.

Give reviewers the original requirement, contracts, diff or artifacts,
validation evidence, and risk boundary. Do not give them the implementer's
expected conclusion.

## Runtime permission observability

The route contract distinguishes behavioral role intent from effective runtime
permissions. Record the live parent permission as `current_sandbox`. Set
`read_only_agent_sandbox_enforced: true` only from positive persisted evidence
for the current host build; a role TOML's `sandbox_mode = "read-only"` is not
sufficient because the host can reapply the parent task's live policy.

Do not gate explorer, reviewer, or advisor routing on permission-mode changes.
They inherit the parent sandbox and remain behaviorally read-only. Persist the
effective sandbox for auditability. Enforce an exact sandbox only when the
human explicitly makes isolation an acceptance criterion; this uses
`inspect_spawn.py --expected-sandbox` and does not alter normal routing.

## Parallelism

Allow read-only work to run concurrently when its questions are independent.
Allow writers to run concurrently only when every write scope is explicit,
non-overlapping, and free from shared generated outputs or hidden dependencies.

Run writers sequentially when scopes overlap or are unknown. Treat an empty
scope as unknown unless the task explicitly declares `read_only: true`.

After parallel implementation, run integration validation and reconcile the
combined artifact before review.

## Evaluation

Log at least:

- Task and profile dimensions with evidence.
- Selected role, model, effort, and routing mode.
- Mandatory gate or escalation reason.
- Validation plan and result.
- Review requirement and findings.
- Latency, tokens, cost, and subscription-quota impact when observable.
- Rework or escalation count.
- Final acceptance result.

Build an evaluation set from real tasks, easy controls, edge cases, costly false
positives, costly false negatives, and previous router failures. Establish a
Sol/high quality baseline, then test whether Terra or Luna meets the same
acceptance threshold. Recalibrate from observed completion, evidence, latency,
and cost rather than intuition.
