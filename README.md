# GPT-5.6 Model Router

An explicit, governed Codex routing plugin. Governance activates only when a
turn contains `$route-gpt56-task`; unrelated delegation is untouched. The root
still decides whether delegation is useful and owns every outcome, while hooks
enforce routed protocol, authority, critical-review, and evidence invariants.

## What it includes

- Validated schema-v4 task profile, recommendation, and route-intent contracts.
- Ten pinned schema-v5 roles on a curated Luna/Terra/Sol effort frontier.
- Plugin-bundled lifecycle hooks that govern routed `Agent` calls before
  execution.
- Atomic, privacy-minimized evidence under `PLUGIN_DATA`.
- Manifest-bound independent Sol/high review for critical work.
- Transactional setup for role templates and effective depth two.
- Python 3.9+ support through a bundled TOML compatibility implementation.

## Use

```text
$setup-gpt56-model-router Install and verify the router.
$route-gpt56-task Implement this change using autonomous cost-aware routing.
```

Both skills remain explicit-only. The root model is unchanged.

Hook execution requires review and trust through `/hooks`. Installation never
auto-trusts plugin hooks.

## Design and release status

- [v0.4.0 implementation and release plan](docs/release-v0.4.0-plan.md)
- [Model and effort decision](plugins/gpt-5-6-model-router/skills/route-gpt56-task/references/model-effort-research.md)
- [Routing policy](plugins/gpt-5-6-model-router/skills/route-gpt56-task/references/routing-policy.md)

## Development validation

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py
python3 scripts/validate_publication.py
python3 scripts/build_publication.py
python3 plugins/gpt-5-6-model-router/skills/setup-gpt56-model-router/scripts/inspect_plugin_discovery.py --marketplace-path .agents/plugins/marketplace.json --json
```

The historical autonomy-first release remains available at tag `v0.3.0`.
