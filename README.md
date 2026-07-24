# GPT-5.6 Model Router

A governed Codex routing plugin. Once its hooks are trusted, every root
`Agent` spawn must be prepared through the router, including delegation on
turns that do not explicitly invoke `$route-gpt56-task`. The root still decides
whether delegation is useful, may work directly on any model and effort, and
owns every outcome.

## What it includes

- Validated schema-v4 task profile, recommendation, and route-intent contracts.
- Eight pinned schema-v5 roles on a five-combination Luna/Terra/Sol frontier.
- Plugin-bundled lifecycle hooks that deny unprepared or invalid `Agent` calls
  before execution.
- Atomic, privacy-minimized evidence under `PLUGIN_DATA`.
- Manifest-bound independent Sol/high review for critical work.
- Transactional setup for role templates and exact effective depth one.
- Python 3.9+ support through a bundled TOML compatibility implementation.

## Use

```text
$setup-gpt56-model-router Install and verify the router.
$route-gpt56-task Implement this change using autonomous cost-aware routing.
```

Both skills remain explicit-only in discovery. Hook enforcement is global for
root `Agent` spawns after trust; ordinary root-only turns remain unaffected.
The router never constrains the root model or root reasoning effort.

Hook execution requires review and trust through `/hooks`. Installation never
auto-trusts plugin hooks.

## Design and release status

- [v0.4.0 implementation and release plan](docs/release-v0.4.0-plan.md)
- [v0.4.1 catalog contraction](docs/catalog-v0.4.1.md)
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
