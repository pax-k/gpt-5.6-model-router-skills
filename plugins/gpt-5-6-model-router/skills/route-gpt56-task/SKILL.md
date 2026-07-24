---
name: route-gpt56-task
description: Prepare governed GPT-5.6 route intents and exact Agent spawn requests while trusted hooks enforce routing, authority, critical-review, ownership, and evidence invariants for every root spawn.
---

# Route GPT-5.6 work with governed autonomy

This skill remains explicit-only in discovery. Once the plugin hooks are
trusted, however, every root `Agent` spawn on every turn must pass through
`route_guard.py prepare` and use its exact emitted `spawn_request`.

The root owns the result and decides whether delegation has positive expected
value. Root-direct execution remains valid on any root model or effort. An
explicit `$route-gpt56-task` turn also registers root-direct work before
closeout; an ordinary root-only turn needs no intent.

## Route on two independent axes

Choose model family from ambiguity, required judgment, and risk:

- Luna/high for clear, repeatable, low-risk mechanical work that still benefits
  from strong verification.
- Terra for bounded implementation, exploration, and evidence-led
  investigation.
- Sol for ambiguity, architecture, cross-layer work, difficult debugging,
  critical risk, independent review, and escalation.

Choose effort from exploration and verification burden:

- medium for ordinary repository reasoning;
- high for competing hypotheses, complex logic, edge cases, or review;

Do not create routes outside the bundled eight-role frontier. Low, xhigh, and
max remain valid runtime efforts but are not custom-agent routes in v0.4.1. See
`references/model-effort-research.md`.

## Register before execution

Use one workstream at a time:

```bash
python3 <skill-directory>/scripts/route_guard.py prepare \
  --input <route-intent-v4.json> \
  --state-dir <PLUGIN_DATA>/governor \
  --session-id <session-id> \
  --turn-id <turn-id> \
  --json
```

The `UserPromptSubmit` hook supplies the active state directory, session, and
turn values. Construct a schema-v4 task profile and route intent. Schema v3 is
rejected; follow `references/migration-v0.4.md`.

- On an explicit router turn using root-direct execution, use
  `execution_mode: "root"` and register before changing state.
- For delegation, use `execution_mode: "delegate"` and pass the emitted
  `spawn_request` to `Agent` exactly.
- For inherited full-history execution, use `execution_mode: "inherited"`,
  `fork_turns: "all"`, an accountable override, and no custom role/model/effort
  fields.

Do not paste source files, diffs, logs, the parent conversation, `AGENTS.md`, or
repository documentation into handoffs. Send objectives, canonical paths,
owned paths, essential constraints, and verification commands. Never include
credentials or secret-like values.

## Authority and overrides

The recommendation is the enforced delegated route. Selecting a different
route requires an override containing reason code, rationale, authority, and
reference, with `user`, `task_contract`, or `recorded_failure` authority.
Root rationale alone cannot change the selected agent, model, or effort.

`quality_first`, delegated critical-floor exceptions, or skipped critical
review require `user`,
`task_contract`, or `recorded_failure` authority. Root rationale alone is not
sufficient. Recorded Sol/high failure is replanned at the Sol/high ceiling
rather than escalating effort.

The router never constrains the root model or root reasoning effort. Critical
root-direct work still requires a current manifest-bound independent Sol/high
review before closeout.

## Delegate compactly

Every routed child is a leaf at depth one. `delegation_grant` must be `none`;
children cannot register descendants or spawn subagents.

Parallel writers require disjoint owned paths. Serialize equal or overlapping
ownership. Children have no commit, tag, or push authority unless their intent
explicitly grants it.

## Bind critical review

Critical execution uses at least Sol/medium unless privileged authority records
an exception. After the change converges, snapshot its canonical owned paths:

```bash
python3 <skill-directory>/scripts/route_guard.py snapshot \
  --state-dir <PLUGIN_DATA>/governor \
  --session-id <session-id> \
  --turn-id <turn-id> \
  --intent-id <source-intent-id> \
  --json
```

Register a separate Sol/high reviewer with `review_target.source_intent_id` and
the returned manifest SHA-256. Any subsequent owned-path change invalidates the
review.

Before closeout, run `route_guard.py audit` or `status`. Structural violations,
unfinished routed work, and missing or stale critical review block closeout.
Unavailable runtime metadata is reported as a warning and must not be claimed
as proof.

## Boundaries

Trusted hooks are enforceable guardrails, not an adversarial security boundary.
Specialized tool paths may bypass normal hooks, hooks can be disabled, and
subagents inherit the active sandbox and approval state.

See `references/routing-policy.md` for enforced rules and
`references/runtime-evidence.md` for fresh-install acceptance.
