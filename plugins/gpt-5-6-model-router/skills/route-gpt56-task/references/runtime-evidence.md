# Runtime evidence boundary v0.4

Unit tests prove contract validation, pure routing, hook-event behavior, state
atomicity, privacy, setup safety, and package structure. They do not prove that
a specific installed Codex host trusted the hooks, reloaded the schema-v5
roles, or persisted the requested child identity.

## Fresh-candidate acceptance

1. Install the exact cachebusted candidate.
2. Start a fresh Codex task.
3. Open `/hooks`, review the hook source, and trust its current hash. Never use
   installation code to auto-trust it.
4. Run `setup_router.py check --json`; confirm stable enabled `hooks` and
   `multi_agent`, eight schema-v5 roles, and effective depth exactly one.
5. Run `inspect_plugin_discovery.py` and verify the exact installed version and
   both explicit skills through `plugin/read`.
6. On an ordinary turn without `$route-gpt56-task`, attempt one unprepared
   `Agent` spawn and prove `PreToolUse` denies it before any child starts.
7. Run valid Luna/high, Terra/medium, and Sol/medium routes.
8. Run one critical route, snapshot its owned paths, complete a separate
   Sol/high review, and prove a post-review change invalidates the review.
9. Run one ordinary root-only turn and prove direct work is unaffected; then
   prepare a valid route on a non-explicit turn and prove its spawn succeeds.
10. Audit governed state and verify it contains hashes and metadata but no raw
    prompt, objective, message, tool output, diff, log, or secret.

## Persisted runtime identity

For every acceptance child, use `inspect_spawn.py` with a unique task name,
root parent thread ID, UTC not-before time, expected role/model/effort, and
expected fork:

```bash
python3 <skill-directory>/scripts/inspect_spawn.py \
  --agent-path /root/<task-name> \
  --not-before <ISO-8601-UTC> \
  --expected-agent <role> \
  --routing-mode custom-agent \
  --parent-thread-id <parent-thread-id> \
  --task-name <task-name> \
  --expected-fork-turns none \
  --json
```

Persisted rollout metadata, not child self-attestation, is the identity proof.
Verify role, model, reasoning effort, parent chain, depth, and the matching
parent spawn request. When any field is unavailable, record a visible warning
and the accountable override path; do not infer success.

## Discovery boundary

Both skills set `policy.allow_implicit_invocation: false`. Their absence from
the ambient model skill catalog is expected. Explicit availability is the
contract: verify through `plugin/read`, then invoke `$route-gpt56-task` or
`$setup-gpt56-model-router`.

## Sandbox boundary

Subagents inherit the parent turn's runtime sandbox and approval choices.
Role-template `sandbox_mode = "read-only"`, hook command checks, and pre/post
HEAD comparison are guardrail evidence, not adversarial isolation. Claim
strict isolation only when an explicit persisted sandbox assertion passes.

Specialized tool paths may bypass normal tool hooks, hooks can be disabled, and
managed configuration can allow only managed hooks. Treat those cases as an
enforcement gap, not a successful governed run.
