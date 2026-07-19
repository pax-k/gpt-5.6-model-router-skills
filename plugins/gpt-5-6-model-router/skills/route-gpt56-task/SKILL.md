---
name: route-gpt56-task
description: Explicitly create or re-enter an autonomous GPT-5.6 routing workflow, select an evidence-backed route, and delegate only through an enforceable custom-agent or model-override contract. Use only when the user invokes this skill by name or a parent capability explicitly permits re-entry.
---

# Route a GPT-5.6 workflow

Keep the root task's model unchanged. This is an explicit-only skill at the
root. A descendant may re-enter it only when the parent passed an unexpired,
bounded delegation capability. Do not infer re-entry permission from a role,
task name, model, or previous child result.

## Runtime authority and references

The v0.2 scripts, schema-2 TOMLs, and tests are the runtime authority. All
bundled design references are implemented contracts except
`references/model-effort-research.md`, which is calibration evidence rather
than a route guarantee. Read the applicable reference before changing a policy
or protocol:

- `routing-policy.md`: route selection, risk floors, escalation, and review.
- `protocol-schemas.md`: task profiles, decisions, capabilities, events, and
  ledger invariants.
- `orchestration-workflows.md`: the 25 implemented workflow scenarios and
  completion behavior.
- `runtime-evidence.md`: automated, local, and live proof boundaries.
- `migration-v0.2.md`: changed commands and schema-1 migration boundary.
- `open-design-decisions.md`: resolved v0.2 decisions and deferred scope.

## Establish or verify the envelope

At root invocation, create a task profile and initialize the local task graph.
The default is **autonomous execution within the requested scope**. Treat the
explicit invocation and task instructions as authority to make reasonable
semantic choices, use reversible assumptions, modify in-scope local state, and
continue across agent waves without router-authored previews or approval
pauses. Record external, destructive, credentialed, or costly authority in the
task profile and obey it exactly. When the host itself requires confirmation,
use that native mechanism; do not add a second router-specific gate.

For re-entry, verify the incoming capability before any route decision. It must
explicitly limit remaining depth, child/parallel budgets, allowed roles/models,
write scopes, and forbidden actions. Root -> authorized workstream owner ->
leaf is the maximum supported topology. Only an explicitly authorized Terra
explorer or Sol engineer may own a child workstream; every other role is a
leaf.

Persist the graph when recursion, a second wave, more than three nodes,
pause/block, or explicit resumability makes it useful. The orchestration CLI
then uses `.codex/gpt56-router/<task-id>.json` atomically. Simple one-wave work
stays in the task; an explicit `--ledger` makes durability failure blocking.

```bash
ROUTER=<skill-directory>/scripts
python3 "$ROUTER/orchestrate.py" init --input task-profile.json --ledger router-ledger.json --json
python3 "$ROUTER/route_task.py" decide --input task-profile.json --json
```

The CLIs always emit JSON. `route_task.py --kind` is not a v0.2 interface.

## Choose and record a route

Supply the complete task profile rather than selecting a model from a label.
Record task kind, phase, evidence-backed risk dimensions, validation strength,
write ownership, external/destructive/costly boundaries, prior failures, and
the delegation capability (if re-entering). Use the selected route exactly; do
not silently downgrade a risk floor or substitute an unavailable pinned model.

The default ladder is Luna/low, Terra/medium, Sol/medium, then Sol/high.
Terra/high, Sol/xhigh, and Sol/max require the policy's evidence-backed
escalation conditions. Consequential work requires an independent reviewer;
the reviewer must receive the original requirement, artifacts, contracts, and
validation evidence without the implementer's expected conclusion.

## Verify the spawn contract and build the call

Inspect the callable `spawn_agent` schema in the current task before spawning.
Use the spawn-message builder, which emits JSON call arguments and rejects a
call only when the runtime cannot represent the selected agent/model route:

```bash
python3 "$ROUTER/build_spawn_prompt.py" \
  --input spawn-envelope.json \
  --json
```

The input envelope contains `decision`, `bounded_context`,
`acceptance_criteria`, `validation_requirements`, and
`supported_spawn_fields`; it may include `delegation_capability` and the
parent/root capability against which it must attenuate. The returned
`spawn_request` is the directly callable JSON arguments object.

Record the live parent permission in the task profile and bounded context when
it is observable. Treat `current_sandbox` and
`read_only_agent_sandbox_enforced` as evidence, not as delegation gates. Live
parent permissions may override a custom agent's TOML sandbox default, so
explorer, reviewer, and advisor roles can inherit a writable sandbox while
remaining behaviorally read-only through their role instructions.

Do not pause merely to change permission modes or resolve an ordinary product
or implementation choice. Select the best evidence-backed reversible option,
record it, and continue. A real host/tool confirmation may still surface with
requesting-agent and proposed-action provenance. When strict sandbox isolation
is itself an explicit acceptance criterion, pass `--expected-sandbox` to the
inspector and report a mismatch without retroactively misrepresenting the
route.

For a descendant spawn, `bounded_context` must include the actual
`parent_agent_path` and `parent_depth: 1`, and the envelope must include the
parent delegation capability as provenance. The builder rejects descendant
calls without that proof and derives `/root/<owner>/<leaf>` itself; do not add
non-schema provenance fields to the route decision.

Select exactly one compatible mode:

- **Custom-agent mode:** when `agent_type` is exposed, use the selected role.
  This applies its installed TOML role/model/effort contract; live task
  permissions can still override the TOML sandbox default.
- **Model-override mode:** only when `agent_type` is absent and both `model`
  and `reasoning_effort` are exposed. Set `fork_turns: "none"` and inline the
  bundled role instructions. This does not apply the TOML or its sandbox.
- **Unsupported:** if neither route is enforceable, stop before spawning and
  report the exact missing fields.

Never use a custom-agent name as `task_name`. Never change model or effort with
a full-history fork. Retain read-only constraints in the child message as the
role's behavioral boundary and report the effective sandbox separately.

## Require a terminal child envelope

Give every child one bounded outcome, its acceptance criteria, required
validation, write ownership, authority limits, and the terminal-envelope
instruction from the builder. The child must return exactly one JSON object,
without Markdown fences, using schema version 1 and one canonical event type.
The envelope contains `task_id`, `node_id`, `agent_path`, `summary`, outcomes,
discovered work, validation, blockers, questions, risks, write scopes, and
review state. Progress may be reported while running, but completion is
reported only through that terminal envelope.

Preview the next wave, atomically reserve it before spawning, then apply each
child event through the ledger:

```bash
python3 "$ROUTER/orchestrate.py" ready --ledger router-ledger.json --json
python3 "$ROUTER/orchestrate.py" dispatch --ledger router-ledger.json --json
python3 "$ROUTER/orchestrate.py" apply-event --ledger router-ledger.json --event child-event.json --json
python3 "$ROUTER/orchestrate.py" status --ledger router-ledger.json --json
python3 "$ROUTER/orchestrate.py" complete-check --ledger router-ledger.json --json
```

Human pause, resume, cancellation, redirection, decision resolution, blocker
resolution, and scope changes use a root-only control envelope:

```bash
python3 "$ROUTER/orchestrate.py" control --ledger router-ledger.json --control human-control.json --json
```

Run independent read-only work concurrently only when questions are actually
independent. Run writers sequentially unless every write scope is explicit,
non-overlapping, and excludes shared outputs/configuration/migrations. Return
new work, exhaustion, blockers, and conflicts to the parent rather than
silently expanding authority. Resolve ordinary semantic decisions locally and
record the chosen assumption. Discovered work from a leaf
remains undispatched until the root re-profiles it; only a valid, attenuated
delegation capability makes an owner's direct descendants schedulable.

## Verify runtime evidence

After spawning, inspect persisted metadata rather than trusting a child's
self-description. The live inspector requires an obtainable spawn identifier
or agent path and a `--not-before` boundary; use optional expected parent,
depth, and sandbox assertions when the task contract provides them:

```bash
python3 "$ROUTER/inspect_spawn.py" \
  --agent-path <agent-path> \
  --not-before <ISO-8601-time> \
  --expected-agent <selected-agent> \
  --routing-mode <custom-agent-or-model-override> \
  --json
```

Use runtime evidence accurately:

- automated fixtures prove parser and contract behavior only;
- local setup checks prove installed local state only; and
- a matching persisted rollout proves that particular live child route only.

If the runtime does not expose a usable identifier-to-rollout bridge, state
that live route proof is unavailable. Do not claim the selected role/model was
applied. A nonzero inspector result, model/effort mismatch, unexpected role,
or inherited root model is a route failure.

## Finish only at the root

Only the root evaluates `complete-check` and completes the human request. It
must verify requested outcomes, required artifacts, validation, mandatory
review and finding resolution, task-graph closure, and disclosure of remaining
blockers, partial results, external actions, and residual risks.
