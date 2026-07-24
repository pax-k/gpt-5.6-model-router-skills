---
name: setup-gpt56-model-router
description: Install, verify, upgrade, or uninstall the eight schema-v5 GPT-5.6 roles and managed depth-one capability, and verify stable hook and multi-agent runtime support.
---

# Set up the GPT-5.6 model router

Python 3.9 or newer and a Codex runtime reporting stable enabled `hooks` and
`multi_agent` features are required.

```bash
python3 <skill-directory>/scripts/setup_router.py install --json
python3 <skill-directory>/scripts/setup_router.py check --json
python3 <skill-directory>/scripts/setup_router.py uninstall --json
```

`install` preflights templates, runtime features, and depth before mutation. It
installs eight schema-v5 roles and ensures effective depth is exactly one.
Existing values are backed up and restored on uninstall. An intact router-owned
depth-two entry is contracted automatically; a managed entry edited after
installation is never overwritten. Failed post-install verification rolls
template and depth changes back together.

Byte-identical schema-2, schema-3, schema-4, and prior schema-5 templates
upgrade automatically after backup. Upgrading also backs up and removes
byte-identical retired Sol/xhigh and Sol/max templates. Modified current or
retired templates are refused unless `install --force`; force never bypasses
depth ownership. Backups remain outside custom-agent discovery.

The plugin bundles lifecycle hooks. Installation and enablement do not trust
them automatically. After install or upgrade:

1. Start a fresh Codex task so plugin and role discovery reload.
2. Open `/hooks`.
3. Review the plugin-bundled hook definition and trust its current hash.
4. Run `setup_router.py check --json`.
5. Run the acceptance scenarios in the route skill's
   `references/runtime-evidence.md`.

If hooks are disabled, untrusted, managed-only, or unsupported, the governed
router is not active. Do not describe skills-only behavior as equivalent.

Subagents inherit the active sandbox and approval state. A role requesting
`read-only` is behavioral evidence unless persisted runtime metadata proves the
expected sandbox.
