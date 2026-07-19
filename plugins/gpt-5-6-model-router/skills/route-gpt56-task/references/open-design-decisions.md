# v0.2 design decisions

Status: Resolved and implemented for v0.2. The selections below define the
released boundary; they are not invitations for a child agent to expand its own
authority. Future changes require a new explicit decision record and migration.

## Contents

- [Orchestration and recursion](#orchestration-and-recursion)
- [Routing and risk](#routing-and-risk)
- [Human interaction and state](#human-interaction-and-state)
- [Runtime and rollout](#runtime-and-rollout)
- [Decision record](#decision-record)

## Orchestration and recursion

### 1. Who owns orchestration?

- A: Root-only; children always return work upward.
- B: Hybrid; root normally orchestrates, while explicitly authorized children
  may spawn one bounded specialist layer.
- C: Recursive tree; every routed agent may delegate freely.

Implemented selection: **B**, for downstream delegation with bounded visibility.

### 2. How does the routing skill activate?

- A: Explicit user invocation only.
- B: Automatic whenever Codex judges routing useful.
- C: Explicit root invocation establishes an envelope; authorized descendants
  may re-enter routing within that task.

Implemented selection: **C**, to avoid globally implicit routing while supporting a
multi-wave task.

### 3. How deep may delegation go?

- A: Depth 1; root to workers only.
- B: Depth 2; root to workstream owner to leaf.
- C: Depth 3 or greater.

Implemented selection: **B**, because it covers meaningful recursion without broad
fan-out.

### 4. Which agents may spawn descendants?

- A: Root only.
- B: Root plus explicitly authorized Terra explorers and Sol engineers.
- C: Every role.

Implemented selection: **B**; keep workers, debuggers, and reviewers narrow by default.

### 5. What authorizes child delegation?

- A: Permanent role permission.
- B: Per-spawn capability with remaining depth, child limit, roles, scopes, and
  forbidden actions.
- C: Child judgment.

Implemented selection: **B**, because delegation is authority rather than a convenience.

## Routing and risk

### 6. How are tasks classified?

- A: Six task labels only.
- B: Task kind plus ambiguity, consequence, breadth, irreversibility,
  verification, latency, failure, phase, and scope dimensions.
- C: Free-form model choice by the orchestrator.

Implemented selection: **B**, combining model judgment with deterministic policy.

### 7. How broad is the route matrix?

- A: Preserve only Luna/low, Terra/medium, Sol/medium, and Sol/high.
- B: Support every model and effort combination equally.
- C: Preserve the core ladder and expose advanced routes only through evaluated
  escalation.

Implemented selection: **C**.

### 8. How is high-risk work handled?

- A: Manual consequential flag.
- B: Automatic risk floors and independent review triggers.
- C: Sol/high review for every write.

Implemented selection: **B**, because manual-only flags are fragile and universal review
is wasteful.

### 9. What happens after failure?

- A: Retry the same route first.
- B: Diagnose the failure, improve evidence or scope, and escalate through the
  core ladder.
- C: Move directly to Sol/max.

Implemented selection: **B**.

### 10. How does parallel execution work?

- A: Read-only parallelism only.
- B: Read-only concurrency plus writers with explicit non-overlapping scopes.
- C: Optimistic concurrent writes followed by conflict resolution.

Implemented selection: **B**.

## Human interaction and state

### 11. What does every child return?

- A: Natural-language report.
- B: Structured event envelope with status, evidence, validation, work
  discovery, risk, and unresolved state.
- C: Direct child-to-child handoff without returning to the parent.

Implemented selection: **B**.

### 12. Where does orchestration state live?

- A: Thread context only.
- B: A state file in every user repository.
- C: Thread state by default plus an optional durable artifact for long-running
  or resumable work.

Implemented selection: **C**.

### 13. Who decides completion?

- A: Root judgment without formal gates.
- B: Last worker.
- C: Root-controlled deterministic completion gate covering outcomes,
  validation, review, and unresolved work.

Implemented selection: **C**.

### 14. What is the default human-control mode?

- A: Supervised; approve every wave.
- B: Bounded autonomy; continue safe local work and ask only at defined
  authority boundaries.
- C: Fully autonomous until completion.

Implemented selection: **C**. Autonomy remains confined to the recorded task
scope, capability, budgets, and host policy.

### 15. How are human questions handled?

- A: Each child may ask the human directly.
- B: Children return decision requests to the root, which consolidates and asks
  once; runtime approvals may still surface with provenance.
- C: Agents decide all semantic ambiguity without asking.

Implemented selection: **C**. Children and the root make evidence-backed,
reversible semantic choices and record them. Host-native runtime approvals may
still surface with provenance.

## Runtime and rollout

### 16. How strict is runtime compatibility?

- A: Require `agent_type` custom agents.
- B: Prefer custom agents, support explicit model plus effort override with
  inlined role instructions, and fail if neither is enforceable.
- C: Spawn an inherited-model child when routing controls are absent.

Implemented selection: **B**.

### 17. How is recursive configuration installed?

- A: Documentation tells users to set `agents.max_depth = 2`.
- B: Normal setup automatically edits global configuration.
- C: A separate explicit setup action validates, backs up, enables, verifies,
  and can roll back depth-two routing.

Implemented selection: **C**.

### 18. What happens when a descendant exhausts its budget?

- A: Fail the entire task.
- B: Return undispatched work upward for parent or root routing.
- C: Automatically request a larger budget from the human.

Implemented selection: **B**.

### 19. What is the optimization objective?

- A: Quality-first; start with Sol/high and down-route after evaluation.
- B: Efficiency-first; start with the cheapest plausible route and escalate on
  failure.
- C: Risk-adjusted; use the cheapest route satisfying correctness,
  consequence, verification, and runtime-enforcement floors.

Implemented selection: **C**.

### 20. What is the first implementation boundary?

- A: Root-managed dynamic waves only.
- B: Root-managed waves and depth-two recursion together.
- C: Dynamic waves, recursion, durable state, evaluation harness, and setup
  changes in one release.

Implemented selection: **B**, for root-managed waves and depth-two, capability-gated recursion.

## Decision record

| Decision | Selection | Notes | Status |
| --- | --- | --- | --- |
| 1. Orchestration owner | B | Root normally orchestrates; an authorized child may own one bounded branch. | Implemented |
| 2. Skill activation | C | Explicit root invocation; capability-gated descendant re-entry only. | Implemented |
| 3. Delegation depth | B | Maximum root -> workstream owner -> leaf. | Implemented |
| 4. Delegation-capable roles | B | Explorer/engineer only when a capability grants it. | Implemented |
| 5. Delegation authorization | B | Per-spawn capability bounds depth, budgets, roles, scopes, and forbidden actions. | Implemented |
| 6. Task classification | B | Kind plus structured evidence/risk dimensions and phase. | Implemented |
| 7. Route matrix | C | Core ladder plus evidence-gated advanced routes. | Implemented |
| 8. Risk policy | B | Automatic risk floors and independent review requirements. | Implemented |
| 9. Failure escalation | B | Diagnose, improve evidence/scope, then escalate. | Implemented |
| 10. Parallelism | B | Parallel read-only work; writers only with explicit disjoint scopes. | Implemented |
| 11. Child result protocol | B | One schema-1 terminal JSON envelope. | Implemented |
| 12. State persistence | C | Task state by default; optional durable local ledger. | Implemented |
| 13. Completion authority | C | Root-only completion gate. | Implemented |
| 14. Human-control mode | B | Bounded autonomy with explicit authority stops. | Implemented |
| 15. Human question routing | B | Children return questions upward; root consolidates. | Implemented |
| 16. Runtime compatibility | B | Custom agent preferred; model override supported; otherwise fail closed. | Implemented |
| 17. Recursive setup | C | Explicit, verified, reversible recursion manager. | Implemented |
| 18. Budget exhaustion | B | Return undispatched work upward. | Implemented |
| 19. Optimization objective | C | Cheapest route satisfying quality, consequence, verification, and enforcement floors. | Implemented |
| 20. First implementation boundary | B | Root waves and depth-two capability-gated recursion. | Implemented |
