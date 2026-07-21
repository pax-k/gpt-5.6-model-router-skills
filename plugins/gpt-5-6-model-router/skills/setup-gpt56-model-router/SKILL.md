---
name: setup-gpt56-model-router
description: Install, verify, upgrade, or uninstall the ten schema-4 GPT-5.6 roles and the managed depth-2 capability through one transactional setup command.
---

# Set up the GPT-5.6 model router

Use the unified workflow for all setup operations:

```bash
python3 <skill-directory>/scripts/setup_router.py install --json
python3 <skill-directory>/scripts/setup_router.py check --json
python3 <skill-directory>/scripts/setup_router.py uninstall --json
```

`install` preflights templates and depth before mutation, installs ten schema-4 roles, and ensures `agents.max_depth >= 2`. Existing values above 2 are preserved. A depth entry changed after router ownership is never overwritten. If post-install verification fails, template and depth mutations roll back together.

Byte-identical schema-2 and schema-3 templates upgrade automatically after backup. Modified templates are refused unless `install --force`; force applies only to templates and never bypasses depth ownership. Backups live outside custom-agent discovery.

A trusted legacy router-owned depth-2 configuration is adopted without losing its original restoration value. `uninstall` restores only the prior managed depth entry when ownership remains intact, preserves unrelated later config edits, and removes only router templates unless explicitly forced.

After install or upgrade, start a fresh Codex task so role discovery reloads. Run `inspect_plugin_discovery.py` to verify the exact installed version and both explicit skills, then use the canaries in `references/runtime-evidence.md`. Treat sandbox mode as observational unless an explicit sandbox assertion passes.
