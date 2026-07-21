# GPT-5.6 Model Router

An explicit, autonomy-first Codex routing plugin. Once `$route-gpt56-task` is invoked, the root decides whether delegation is worthwhile, chooses and coordinates useful workstreams, and may override every model, effort, fork, review, or escalation default.

The defaults target best expected value: cheapest adequate execution unless stronger reasoning or parallelism brings meaningful quality or latency benefit.

## What it includes

- Advisory recommendation schema v3 for Luna, Terra, and Sol routes.
- Ten pinned schema-4 roles with a default-leaf and exact one-level descendant contract.
- An optional compact routed-handoff helper supporting empty or bounded forks; full-history spawns inherit the parent route and remain outside the helper.
- Advisory independent Sol/high review for critical work, with no fixed repair-cycle limit.
- Unified transactional setup for role templates and `agents.max_depth >= 2`.
- Safe schema-2/schema-3 migration, ownership-aware uninstall, and install-time runtime inspection.

The router does not require production scoring, mandatory delegation, fixed fan-out, exact-route compliance, or fail-closed fallbacks. Scripts are optional evaluation and troubleshooting tools.

## Use

```text
$setup-gpt56-model-router Install and verify the router.
$route-gpt56-task Implement this change using autonomous cost-aware routing.
```

Both skills remain explicit-only. The root model is unchanged.

## Development validation

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py
python3 scripts/validate_publication.py
python3 scripts/build_publication.py
python3 plugins/gpt-5-6-model-router/skills/setup-gpt56-model-router/scripts/inspect_plugin_discovery.py --marketplace-path .agents/plugins/marketplace.json --json
```

The historical orchestration release remains available at tag `v0.2.2`. See the v0.3 migration guide in the route skill.
