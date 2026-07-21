# Runtime evidence boundary v0.3

Local tests prove route policy, message budgets, setup safety, and publication structure. They do not prove that Codex exposes the installed explicit skills or that a running task reloaded newly installed custom agents.

After installation or a schema-2/schema-3 upgrade:

1. Restart Codex or start a fresh task after the host reload boundary.
2. Run `inspect_plugin_discovery.py` against the configured marketplace. It uses Codex's `plugin/read` API to verify the exact installed version and both enabled explicit skills.
3. Run `setup_router.py check --json` and confirm ten schema-4 templates plus effective depth at least 2.
4. Spawn one root child with `fork_turns: "none"` and `Delegation grant: one-level`; have it create one useful descendant carrying `Delegation grant: none`.
5. Spawn a second no-grant child and verify it remains a leaf.
6. Record unique task names, the root parent thread ID, canonical agent paths, and a UTC not-before timestamp.
7. Use `inspect_spawn.py` for each relevant rollout. Verify persisted role, model, reasoning effort, parent chain, depth, and matching parent fork provenance.
8. Treat sandbox as observational unless the acceptance requires strict isolation and passes `--expected-sandbox`.
9. Record discovery, setup, one-level, and no-grant checks as install acceptance.

```bash
python3 <setup-skill-directory>/scripts/inspect_plugin_discovery.py \
  --marketplace-path <absolute-marketplace.json-path> \
  --json
```

Both skills set `policy.allow_implicit_invocation: false`. Their absence from the ambient model skill catalog is therefore expected and must not be reported as a discovery failure. Explicit availability is the supported contract: verify it through `plugin/read`, then invoke the skill with `$route-gpt56-task` or `$setup-gpt56-model-router` in the composer.

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

The child rollout may not persist `fork_turns`. Fork proof therefore comes from the matching parent spawn request, keyed by the required unique task name. If either rollout or the matching request is unavailable, report runtime proof as unavailable rather than inferring success.

Role templates may request `read-only` while the host persists a broader inherited sandbox. That remains behavioral read-only, not sandbox isolation. Claim strict isolation only when an explicit `--expected-sandbox` assertion passes.

Do not inspect ordinary production spawns. Per-task inspection adds latency and context without improving routing after the installation contract is established. Re-run the canaries only after setup changes, runtime upgrades, or troubleshooting evidence suggests drift.

The fixed child-context floor supplied by Codex remains outside plugin control. Version 0.3 reduces router-generated prompt material and avoids unnecessary workstreams while allowing useful independent fan-out. Measure the 50% raw-token reduction target across a representative complete task, not per child, while holding quality and validation constant.
