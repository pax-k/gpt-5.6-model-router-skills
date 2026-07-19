# Runtime evidence contract

Status: Implemented v0.2 evidence boundary.

Routing claims must name the strongest evidence actually available. Do not
upgrade a fixture, local setup result, or child self-report into proof that a
hosted runtime applied a model or role.

## Evidence levels

| Level | Artifact | Supported claim | Excluded claim |
| --- | --- | --- | --- |
| Automated repository proof | Unit tests, 25 workflow fixtures, validator output | Local parsing, policy, state transitions, and expected metadata checks behave according to the versioned contract | A real account/client exposed the required spawn fields or accepted a call |
| Local setup proof | `manage_agents.py` / `manage_recursion.py` JSON check results | The local templates/config are present, match the manager's ownership rules, or were reversibly changed | The active task has reloaded those files or may delegate recursively |
| Live runtime proof | Inspector JSON matched to a post-spawn persisted rollout | This actual child route matched expected role/mode, model, effort, and available provenance/sandbox assertions | Other tasks, clients, accounts, workspace policies, or future versions behave the same |

## Live inspection requirements

Live inspection requires a route-specific search boundary and expected route:

```bash
python3 scripts/inspect_spawn.py \
  --agent-path <agent-path> \
  --not-before <ISO-8601-time> \
  --expected-agent <role> \
  --routing-mode <custom-agent-or-model-override> \
  --json
```

The optional `--thread-id`, repeatable `--sessions-root`, expected parent,
depth, and sandbox inputs make the evidence more specific when the runtime
exposes those values. The inspector output records actual and expected model,
effort, role, provenance, depth, sandbox, and `failure_reasons`.

For custom-agent mode, the expected role must match. For model-override mode,
the role must be absent while model and effort match, because the TOML was not
applied. A missing identifier-to-rollout bridge means **live proof unavailable**
and must be reported as such; do not fabricate a thread ID or infer proof from
agent prose.

## Reporting language

Use precise wording:

- “Automated repository proof passed” for fixtures/validator only.
- “Local setup check passed” for agent/recursion manager output only.
- “Live runtime route verified for this child” only after a matching inspector
  result.
- “Live runtime proof unavailable” when a compatible spawn schema or rollout
  bridge is absent.

If runtime fields are absent, route failure is the correct result. Never spawn
an inherited-model child while claiming the selected route was enforced.

## Release acceptance summary

Before the v0.2 public release, the repository passed its full automated suite,
repository validator, both official skill validators, the official plugin
validator, local installation checks, reversible recursion checks, and fresh
Desktop runtime acceptance.

The runtime exercises covered every managed role/model/effort identity, a
root-managed multi-wave graph, one authorized depth-two owner-to-leaf flow,
budget return, malformed-event normalization, validation-driven escalation,
the lower-tier-root advisory gate, and independent consequential review.

One host boundary was observed and retained in the contract: effective sandbox
permissions can inherit from the parent runtime even when a role template
declares read-only. Read-only agents are therefore behaviorally constrained by
their role instructions, while strict sandbox isolation is claimed only when
the inspector receives and passes an explicit `--expected-sandbox` assertion.

Machine-specific rollout identifiers, local paths, and raw acceptance records
are deliberately excluded from the published plugin. Maintainers retain those
artifacts privately and can reproduce the public claims with the repository
test suite and a fresh runtime acceptance task.
