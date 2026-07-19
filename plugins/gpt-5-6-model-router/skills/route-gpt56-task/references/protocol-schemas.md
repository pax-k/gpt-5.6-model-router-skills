# Routing and delegation protocols

Status: Implemented v0.2 protocol contract. The JSON schemas are exercised by
the structured route, spawn, orchestration, inspection, and workflow-fixture
tests. Examples are illustrative values, while the scripts define parsing and
validation details.

## Contents

- [Runtime route modes](#runtime-route-modes)
- [Task profile](#task-profile)
- [Route decision](#route-decision)
- [Delegation capability](#delegation-capability)
- [Child event envelope](#child-event-envelope)
- [Task graph](#task-graph)
- [Completion record](#completion-record)
- [Protocol invariants](#protocol-invariants)

## Runtime route modes

Inspect the current agent's callable spawn schema at every delegation level.
Select exactly one mode:

- `custom_agent`: use `agent_type`; apply the installed TOML model, effort,
  instructions, and declared defaults. The live parent permission may override
  the TOML sandbox default.
- `model_override`: use explicit `model` and `reasoning_effort` with
  `fork_turns: "none"`; inline the selected role instructions because the TOML
  is not applied.
- `unsupported`: stop before spawning when neither enforceable route exists.

Never put a role name into `task_name` as a substitute for `agent_type`. Never
use a full-history fork when changing model or effort because the child inherits
the parent route. Verify persisted runtime metadata rather than child
self-attestation.

`inspect_spawn.py` accepts the canonical agent path returned by spawning plus a
freshness boundary, resolves the matching persisted rollout, and recovers the
real child thread ID. Treat that persisted metadata as route evidence; do not
use child self-identification.

Read-only roles inherit the parent task's effective permissions. The task
profile and spawn context may state `current_sandbox`, while
`read_only_agent_sandbox_enforced` may be true only with positive current-build
persisted evidence. These fields support observability and strict opt-in
acceptance checks; they do not block normal routing.

## Task profile

```json
{
  "schema_version": 1,
  "task_id": "00000000-0000-4000-8000-000000000001",
  "node_id": "00000000-0000-4000-8000-000000000001",
  "objective": "Migrate session validation without breaking active clients",
  "kind": "ambiguous",
  "phase": "implementation",
  "dimensions": {
    "ambiguity": {"rating": 3, "evidence": "Multiple compatible migration designs"},
    "consequence": {"rating": 3, "evidence": "Authentication boundary"},
    "context_breadth": {"rating": 2, "evidence": "Auth package and clients"},
    "irreversibility": {"rating": 2, "evidence": "Persistent session compatibility"},
    "verification_strength": {"rating": 2, "evidence": "Automated tests plus staged checks"},
    "latency_sensitivity": {"rating": 1, "evidence": "Normal delivery window"}
  },
  "risk_domains": ["authentication", "public-api", "migration"],
  "prior_attempts": [],
  "read_only": false,
  "read_scopes": ["packages/auth", "tests/auth"],
  "write_scopes": ["packages/auth", "tests/auth"],
  "dependencies": [],
  "human_authority": {
    "local_writes": true,
    "external_writes": false,
    "destructive_actions": false,
    "quality_first": false
  },
  "orchestrator": {"model": "gpt-5.6-sol", "effort": "medium"},
  "depth": 0,
  "delegation_request": {"requested": true},
  "runtime_capabilities": {
    "agent_type": true,
    "model_override": true,
    "current_sandbox": "danger-full-access",
    "read_only_agent_sandbox_enforced": false
  }
}
```

Require evidence for dimension values and risk domains in the eventual script
input or orchestration ledger. Do not treat an unexplained number as sufficient
for consequential routing.

## Route decision

```json
{
  "schema_version": 1,
  "task_id": "00000000-0000-4000-8000-000000000001",
  "node_id": "00000000-0000-4000-8000-000000000001",
  "decision": "delegate",
  "routing_mode": "custom_agent",
  "primary": {
    "agent": "gpt56_router_sol_debugger",
    "model": "gpt-5.6-sol",
    "reasoning_effort": "high",
    "read_only": false
  },
  "review": {
    "required": true,
    "route": {
      "agent": "gpt56_router_sol_reviewer",
      "model": "gpt-5.6-sol",
      "reasoning_effort": "high",
      "read_only": true
    }
  },
  "advisory": {"required": false, "route": null},
  "delegation_capability": {
    "schema_version": 1,
    "allowed": false,
    "remaining_depth": 0,
    "max_children": 0,
    "max_parallel_children": 0,
    "allowed_roles": [],
    "allowed_models": [],
    "allowed_write_scopes": [],
    "may_spawn_writers": false,
    "forbidden_actions": ["external-writes", "destructive-actions"],
    "required_return": ["child-runtime-evidence", "child-results", "undispatched-work"]
  },
  "parallel_eligibility": {
    "eligible": true,
    "requires_disjoint_peers": true,
    "reason_code": "KNOWN_WRITE_SCOPE_REQUIRES_DISJOINT_PEERS"
  },
  "reason_codes": [
    "KIND_AMBIGUOUS",
    "SOL_HIGH_RISK_GATE",
    "CONSEQUENTIAL_RISK_DOMAIN",
    "INDEPENDENT_REVIEW_REQUIRED"
  ]
}
```

Allow `decision` values `direct_execution`, `delegate`, `ask_human`, `wait`, or
`unsupported`. Make every nontrivial decision explainable through stable reason
codes.

## Delegation capability

Pass this only to an authorized workstream owner:

```yaml
schema_version: 1
allowed: true
remaining_depth: 1
max_children: 3
max_parallel_children: 2
allowed_roles:
  - gpt56_router_luna_worker
  - gpt56_router_terra_explorer
allowed_models:
  - gpt-5.6-luna
  - gpt-5.6-terra
allowed_write_scopes:
  - packages/auth
  - tests/auth
may_spawn_writers: false
forbidden_actions:
  - external-writes
  - destructive-actions
  - credential-changes
required_return:
  - child-runtime-evidence
  - child-results
  - undispatched-work
```

Omit the capability or set `allowed: false` for a leaf. Do not infer delegation
authority from an agent role alone.

At spawn construction, depth-two provenance lives in the bounded context, not
in ad hoc route-decision properties: pass `parent_agent_path`,
`parent_depth: 1`, and the exact parent delegation capability. The builder
validates the proof and derives the nested child path.

## Child event envelope

Require every child to return exactly one terminal event object and no Markdown
fences. Permit progress events while it runs. The canonical v0.2 envelope uses
`event_type` (not the retired `event` field), includes both graph identity and
runtime provenance, and has this complete shape:

```json
{
  "schema_version": 1,
  "event_type": "complete",
  "task_id": "00000000-0000-4000-8000-000000000001",
  "node_id": "00000000-0000-4000-8000-000000000002",
  "agent_path": "/root/session_migration__trace_session_loading",
  "summary": "Session configuration is loaded once at process startup.",
  "outcomes": [
    {
      "kind": "file",
      "location": "packages/auth/src/session.ts:42",
      "claim": "Initialization reads the configuration during module setup."
    }
  ],
  "validation": [
    {
      "command": "pnpm --filter @example/auth test",
      "status": "passed"
    }
  ],
  "discovered_work": [],
  "blockers": [],
  "questions": [],
  "risks": [],
  "write_scopes": [],
  "review": {
    "required": false,
    "status": "not_required",
    "findings": []
  }
}
```

Support these event values:

| Event | Meaning | Parent response |
| --- | --- | --- |
| `progress` | Work continues normally | Update status; do not re-route by default |
| `complete` | Assigned outcome finished | Validate and close node |
| `partial` | Some outcomes finished | Preserve results and route remainder |
| `new_work` | Separate task discovered | Return it for root re-profiling, or create it only under a validated owner capability |
| `needs_decision` | Legacy child did not select among semantic directions | Root selects the recommendation or safest reversible evidence-backed option, records it, and re-queues |
| `approval_required` | Host/tool actually requires confirmation | Preserve action provenance as an external blocker; never emit for router policy |
| `risk_discovered` | Consequence or irreversibility changed | Raise route and review floor |
| `validation_failed` | Objective check failed | Diagnose failure and escalate |
| `blocked` | Work cannot proceed locally | Continue independent work and preserve the external resume condition |
| `conflict` | Evidence disagrees | Create resolution investigation |
| `budget_exhausted` | Local delegation limit reached | Return undispatched work upward |
| `cancelled` | Parent or human stopped the task | Reconcile task graph |
| `failed` | Assigned outcome cannot be delivered | Preserve evidence and re-profile |

## Task graph

```json
{
  "schema_version": 1,
  "root_task_id": "00000000-0000-4000-8000-000000000001",
  "authority_envelope": {
    "mode": "autonomous-within-scope",
    "local_writes": true,
    "external_writes": false,
    "destructive_actions": false
  },
  "budgets": {
    "max_depth": 2,
    "max_open_threads": 6,
    "max_total_spawns": 8,
    "max_children_per_node": 3,
    "max_parallel_children": 2
  },
  "nodes": [
    {
      "task_id": "00000000-0000-4000-8000-000000000002",
      "status": "complete",
      "dependencies": [],
      "route_history": ["gpt56_router_terra_explorer"],
      "required_review": false
    },
    {
      "task_id": "00000000-0000-4000-8000-000000000003",
      "status": "ready",
      "dependencies": ["00000000-0000-4000-8000-000000000002"],
      "route_history": [],
      "required_review": true
    }
  ],
  "outstanding_human_decisions": [],
  "external_blockers": [],
  "remaining_review": ["00000000-0000-4000-8000-000000000003"]
}
```

Use statuses `queued`, `ready`, `running`, `waiting`, `blocked`, `review`,
`repair`, `complete`, `partial`, `failed`, or `cancelled`.

Keep orchestration state in the task by default. Automatically create the
workspace ledger for recursion, a second wave, graphs over three nodes,
pause/block, or explicit resumability. `ready` is a preview; `dispatch` is the
locked reservation transition that marks nodes running and accounts spawn
budgets. Root-only `control` transitions pause, resume, cancel, redirect,
resolve decisions/blockers, or update scopes.

## Completion record

```json
{
  "schema_version": 1,
  "root_task_id": "00000000-0000-4000-8000-000000000001",
  "status": "complete",
  "complete": true,
  "requested_outcomes_satisfied": true,
  "validation_passed": true,
  "required_reviews_complete": true,
  "unresolved_findings": [],
  "ready_or_running_nodes": [],
  "external_actions_taken": [],
  "residual_risks": [],
  "routes_used": [
    "gpt56_router_terra_explorer",
    "gpt56_router_sol_debugger",
    "gpt56_router_sol_reviewer"
  ],
  "unmet_gates": []
}
```

Allow only the main orchestrator to emit the completion record for the human's
overall request.

## Protocol invariants

- Keep the root model unchanged.
- Re-profile newly discovered work rather than inheriting its parent's route.
- Require explicit delegation capability for descendant spawning.
- Treat depth and child limits as authority boundaries.
- Keep semantic human questions consolidated through the root.
- Never let latency or cost lower a mandatory risk floor.
- Never silently substitute an unavailable model or inherited parent model.
- Verify model and effort from runtime evidence rather than self-report.
- Run overlapping or unknown write scopes sequentially.
- Preserve completed evidence when pausing, cancelling, redirecting, or
  resuming.
- Distinguish partial, blocked, failed, cancelled, and complete outcomes.
- Require independent review for consequential work.
- Treat reviewer findings as unresolved until a clean re-review or an explicit
  resolved/closed/dismissed finding state is recorded.
