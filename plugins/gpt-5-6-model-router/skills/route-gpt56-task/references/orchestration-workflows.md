# Human and agent orchestration workflows

Status: Implemented v0.2 workflow contract. Each numbered workflow has a
versioned fixture covering its minimum profile and expected decision or event
transition. Runtime availability and external side effects remain subject to
the evidence boundaries in `runtime-evidence.md`.

## Contents

- [Operating model](#operating-model)
- [Actors and authority](#actors-and-authority)
- [Lifecycle](#lifecycle)
- [Human interaction modes](#human-interaction-modes)
- [Workflow catalog](#workflow-catalog)
- [Completion](#completion)

## Operating model

Represent the user request as an evolving task graph controlled by one
human-facing orchestrator. Agents are temporary workers, workstream owners, or
reviewers. They do not become competing assistants talking independently to the
human.

Compose every workflow from these events:

```text
classify -> execute -> report -> discover -> reclassify
         -> decide from evidence -> record assumption
         -> escalate -> review -> repair -> complete
```

Do not pre-plan a fixed agent tree. Reassess after every material result,
failure, risk discovery, human instruction, or external-state change.

## Actors and authority

### Human

Define goals, constraints, authority, priorities, and irreversible decisions.
Allow the human to steer, pause, cancel, expand, narrow, or request review at
any time.

### Main orchestrator

Keep the main task as the normal human interface. Own:

- Original request and success criteria.
- Task graph, dependency order, and readiness.
- Model, effort, role, and routing-mode selection.
- Delegation depth, child count, concurrency, and authority budgets.
- Consolidated human questions and progress reporting.
- Conflict resolution, review sequencing, and completion judgment.

Allow the orchestrator to execute directly when delegation adds no value.

### Workstream owner

Authorize only selected Terra explorers or Sol engineers to own large,
independent branches. Give them an explicit delegation capability. Without it,
treat them as leaves.

### Leaf worker

Assign one bounded outcome. Require it to return evidence, validation, newly
discovered work, and residual risk. Do not allow it to declare the overall user
request complete.

### Independent reviewer

Give it requirements, contracts, artifacts, evidence, and risk boundaries
without the implementer's expected conclusion. Keep it separate from primary
implementation and make it report findings to the orchestrator.

## Lifecycle

Use these task states:

```text
intake
  -> assumption recording when requirements admit several valid choices
  -> profiling
  -> direct execution or ready queue
  -> running
  -> reassessment
  -> new ready work, escalation, autonomous decision, or review
  -> repair and re-review when findings exist
  -> completion gate
  -> complete, partial, blocked, cancelled, or failed
```

At reassessment, update the task graph from actual evidence rather than the
initial plan.

## Human interaction modes

### Supervised

Propose each agent wave and wait for authorization before spawning. Use this for
experimental, expensive, politically sensitive, or unusually broad tasks.

### Autonomous within an explicit envelope

This is the default. Continue until completion or a genuine blocker under the
explicit goal, task scope, authority fields, spawn budget, and forbidden
actions. Make routine semantic and implementation decisions from evidence,
favor reversible choices, and record assumptions. Do not introduce
router-specific preview or approval gates. Host/tool confirmations may still
surface when the platform requires them.

## Workflow catalog

### 1. Direct execution

Use no child when the task is smaller than the coordination overhead. Inspect,
execute, validate, and report from the main task.

### 2. One-shot delegation

Classify one bounded task, spawn one worker, verify its runtime route, collect
its evidence, validate, and complete.

### 3. Parallel read-only exploration

Spawn independent Terra/medium explorers for runtime tracing, tests,
documentation, or external evidence. Merge facts and uncertainties before
selecting implementation.

### 4. Exploration followed by implementation

Use exploration to narrow the boundary. Re-profile the implementation rather
than inheriting the exploration route. Escalate when exploration reveals
architecture, migration, distributed state, security, or compatibility risk.

### 5. Parallel disjoint implementation

Run writers concurrently only with explicit, non-overlapping ownership. Prevent
concurrent changes to shared generated outputs, configuration, migrations, or
unknown scopes. Run integration validation afterward.

### 6. Sequential dependency pipeline

Activate work only when dependencies complete. A single pipeline may use
different routes for design, migration, API implementation, client work,
fixtures, testing, and review.

### 7. Bounded recursive workstream

Give an authorized workstream owner remaining depth, maximum children, allowed
roles, write scopes, and forbidden actions. Require it to synthesize all child
evidence before returning to the parent.

Prefer root-managed waves. Enable depth-two recursion only when a child truly
owns a large independent branch. Codex defaults `agents.max_depth` to 1; depth
2 permits root, workstream owner, and leaf. Keep deeper recursion disabled until
evaluations justify it.

### 8. New work discovered downstream

Require the child to return a `new_work` or `partial` event instead of silently
expanding scope. Let the orchestrator create, classify, and schedule a new node.

### 9. Validation failure and escalation

Classify the failure before acting:

- Repair a concrete mechanical error with the same model at most once when the
  evidence is decisive.
- Increase effort for insufficient search or checking.
- Increase model tier for missing abstractions or broad-context failure.
- Re-decompose when ownership or task boundaries are wrong.
- Repair the verifier before further implementation when validation is not
  trustworthy.
- Stop identical retries after repeated failure.

### 10. Consequential implementation and review

Route implementation at the required risk floor, run automated validation,
then assign a separate Sol/high reviewer. Enter a bounded review-repair loop
when findings exist.

### 11. Review-repair loop

Revalidate every repair and return it to independent review. Cap materially
similar repair cycles. After repeated failures, return to the orchestrator for
re-decomposition or human direction rather than continuing indefinitely.

### 12. Conflicting agent conclusions

Do not vote or choose the most confident prose. Create a resolution task whose
goal is decisive evidence, reproduction, or an explicit statement that the
conflict is unresolved or version-dependent.

### 13. Semantic decision discovered

Resolve routine semantic choices at the worker or orchestrator using the best
evidence-backed reversible option. Record the chosen assumption and propagate
it to affected nodes. A legacy `needs_decision` event is auto-resolved by the
root and re-queued instead of becoming a human wait state.

### 14. Permission or approval required

Do not create router-specific approvals for product, scope, or implementation
choices. Runtime approvals may surface from a child only when the host or tool
actually requires one; preserve the requesting agent, proposed action, reason,
consequence of rejection, and safer alternatives. Approval never expands
authority beyond the specific action.

### 15. Human changes direction

Determine whether the new instruction replaces, narrows, or adds to the goal.
Stop irrelevant agents, preserve useful completed evidence, cancel obsolete
nodes, invalidate affected assumptions, and re-profile remaining work.

### 16. Human adds scope

Add nodes without repeating completed work. Reassess existing nodes when the
new scope changes architecture, contracts, or acceptance criteria.

### 17. Human asks for status

Report complete, running, waiting, blocked, review-required, and decision-needed
states from the task graph. Do not stop agents unless the human asks to pause.

### 18. Human pauses or cancels

On pause, stop launching new work and preserve resumable state. On cancellation,
interrupt active work, cancel queued nodes, preserve completed artifacts unless
the human explicitly requests removal, and report partial changes. Do not treat
cancellation as authorization for destructive rollback.

### 19. Runtime cannot enforce the route

Fail closed when neither custom-agent selection nor explicit model plus effort
override is available. Do not spawn an inherited-model child while claiming it
used the selected route.

### 20. Selected model unavailable

Surface the exact failure and continue unrelated work. Do not substitute an
unavailable model: re-profile to another canonical route only when the policy
independently selects it from new evidence.

### 21. Depth or spawn budget exhausted

Return undispatched work upward. Let the parent or root route it within its own
remaining authority or defer it. Local budget exhaustion does not
automatically fail the overall task and does not manufacture a human approval
request.

### 22. External dependency blocks one branch

Continue independent ready work. Mark the blocked node with the external owner,
required state change, and resume condition. Report the unresolved dependency
at completion or when no ready work remains.

### 23. Partial success

Distinguish complete outcomes, incomplete outcomes, blockers, artifacts, and
recovery steps. Never report partial completion as full success.

### 24. Resume after interruption or compaction

Restore the original objective, authority envelope, completed evidence, active
and interrupted nodes, dependencies, route history, validation, outstanding
decisions, review requirements, and remaining budgets. Do not repeat completed
work merely because conversational context was compacted.

### 25. Final completion

Allow only the main orchestrator to complete the human request. Require all
requested outcomes, validation, mandatory review, finding resolution, task-graph
closure, and disclosure of residual failures or external actions.

## Completion

Before final completion, verify:

- The original requested outcomes exist.
- Required artifacts are present.
- Required validation passed.
- Consequential work received independent review.
- Review findings were resolved or explicitly disclosed.
- No ready or running nodes remain.
- No partial failure or external dependency is hidden.
- Destructive, external, credentialed, and costly actions stayed within the
  human's authority envelope.

Report outcome, material changes or findings, exact validation evidence,
relevant agent routes, residual risks, and any remaining human or external
action.
