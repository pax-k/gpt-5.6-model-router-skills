---
name: route-gpt56-task
description: Explicitly activate governed GPT-5.6 routing for a task, preserving root autonomy while enforcing routed protocol, authority, critical-review, ownership, and evidence invariants.
---

# Route GPT-5.6 work with governed autonomy

This skill activates only when explicitly invoked. It governs the active turn,
not unrelated delegation in other turns.

The root owns the result and decides whether delegation has positive expected
value. Root-direct execution remains valid. Once governance is active, register every root or delegated workstream before doing or spawning that work.

## Route on two independent axes

Choose model family from ambiguity, required judgment, and risk:

- Luna for clear, repeatable, low-risk mechanical work.
- Terra for bounded implementation, exploration, and evidence-led
  investigation.
- Sol for ambiguity, architecture, cross-layer work, difficult debugging,
  critical risk, independent review, and escalation.

Choose effort from exploration and verification burden:

- low for straightforward latency-sensitive work;
- medium for ordinary repository reasoning;
- high for competing hypotheses, complex logic, edge cases, or review;
- xhigh after recorded lower-route failure;
- max for explicitly authorized hardest quality-first work.

Do not create routes outside the bundled ten-role frontier. In particular,
Terra/low remains experimental and is not a v0.4.0 role. See
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

- For root-direct execution, use `execution_mode: "root"` and register before
  changing state.
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

Ordinary noncritical route choices remain advisory, but selecting a different
route requires an override containing reason code, rationale, authority, and
reference.

`quality_first`, xhigh, max, critical-floor exceptions, critical root-direct
execution without provable effort, or skipped critical review require `user`,
`task_contract`, or `recorded_failure` authority. Root rationale alone is not
sufficient.

## Delegate compactly

Children are leaves unless the intent grants exactly `one-level`. A granted
child may register bounded descendants, but every descendant must use
`Delegation grant: none`.

Parallel writers require disjoint owned paths. Serialize equal, ancestor, or
descendant ownership. Children have no commit, tag, or push authority unless
their intent explicitly grants it.

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

See `references/routing-policy.md` for enforced versus advisory rules and
`references/runtime-evidence.md` for fresh-install acceptance.
