---
name: setup-gpt56-model-router
description: Install, verify, repair, or uninstall the schema-2 autonomous GPT-5.6 custom-agent files, and explicitly manage depth-two routing setup. Use only when the user explicitly invokes this skill.
---

# Set up the GPT-5.6 model router

Manage only the ten `gpt56-router-*.toml` files owned by this plugin. Do not
edit unrelated agent files. Agent setup and recursion setup are separate,
explicit actions; neither silently expands the user's normal Codex authority.

## Manage schema-2 agent templates

Resolve this skill directory, then use the manager for the requested action:

```bash
python3 <skill-directory>/scripts/manage_agents.py check --json
python3 <skill-directory>/scripts/manage_agents.py install --json
python3 <skill-directory>/scripts/manage_agents.py uninstall --json
```

Run `check` before installation and report its JSON evidence. If files are
missing, install them and run `check` again. An identical installation is a
successful no-op.

- Treat a divergent destination as user-owned until the user explicitly
  authorizes `install --force`; an explicit request to install, repair, or make
  the router autonomous counts as that authorization for router-owned files.
- Forced installation backs up every divergent owned filename before replacing
  it. Backups live under `~/.codex/.gpt56-router-agent-backups/`, outside the
  recursively discovered custom-agent directory. Install also migrates legacy
  router backups out of `~/.codex/agents/`.
- Uninstall removes only byte-identical managed templates by default. A
  divergent managed file requires explicit `uninstall --force`, which backs it
  up before removal. Backups and unrelated files remain untouched.
- Never silently substitute models, efforts, role definitions, or old
  schema-1 templates.

After a successful change, tell the user to start a new Codex task so custom
agent discovery reloads the files. Do not change the user's root model.

## Manage bounded recursion separately

Depth-two recursion is opt-in because it enables a root to grant a bounded
workstream owner one specialist layer. It is not free delegation: every child
still needs a per-spawn capability and the policy caps depth, children,
parallelism, roles/models, scopes, and forbidden actions.

Use the recursion manager only when the user asks to enable, inspect, or undo
this capability:

```bash
python3 <skill-directory>/scripts/manage_recursion.py check --json
python3 <skill-directory>/scripts/manage_recursion.py enable --json
python3 <skill-directory>/scripts/manage_recursion.py disable --json
```

`enable` validates and backs up the relevant setting before making a reversible
change. If later unrelated configuration edits leave the ownership marker and
`agents.max_depth = 2` intact, `check` and repeated `enable` remain successful
and report that rollback is guarded. `disable` restores the pre-existing state
only while the complete managed snapshot still matches; it refuses rather than
overwrite later user edits. Do not edit global configuration by hand as a
fallback.

## Evidence boundary

A passing setup/recursion `check` is **local setup proof**. It does not prove
that the currently running client exposes `agent_type`, `model`, or
`reasoning_effort`, nor that a later spawn used a role. Route skill runtime
inspection is required for live proof. If Python is unavailable, stop and ask
the user to run the documented setup command rather than improvising a weaker
filesystem or configuration mutation.
