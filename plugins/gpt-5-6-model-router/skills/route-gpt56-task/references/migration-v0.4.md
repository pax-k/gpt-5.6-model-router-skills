# Migrating from v0.3 to governed v0.4

Version 0.4 is a clean contract break.

## Breaking changes

- `task-profile-v3` is rejected. Use `task-profile-v4`.
- `route-recommendation-v3` is rejected. Use `route-recommendation-v4`.
- `route-intent-v4` is required for root, delegated, and inherited workstreams
  on an active router turn.
- `quality_first: boolean` is removed. Use the authority-bearing
  `quality_mode` object.
- Role-template markers move from schema 4 to schema 5.
- `build_spawn_prompt.py` is removed. `route_guard.py prepare` now emits and
  registers the exact governed spawn request.
- Critical Sol/medium execution and manifest-bound independent Sol/high review
  are enforced unless privileged authority records an exception.

## Quality mode

Standard work:

```json
{
  "quality_mode": {
    "level": "standard",
    "authority": "root",
    "reference": ""
  }
}
```

Authorized quality-first work:

```json
{
  "quality_mode": {
    "level": "quality_first",
    "authority": "task_contract",
    "reference": "release-plan#quality-first"
  }
}
```

`quality_first`, xhigh, or max requires `user`, `task_contract`, or
`recorded_failure` authority and a non-empty reference.

## Installation

Run the transactional installer:

```bash
python3 <setup-skill-directory>/scripts/setup_router.py install --json
```

Byte-identical schema-2, schema-3, and schema-4 roles upgrade after backup.
Modified templates require `--force`; managed depth ownership cannot be
bypassed. Installation verifies stable enabled `hooks` and `multi_agent`
features but never trusts hooks.

Start a fresh Codex task, open `/hooks`, review the plugin hook definition, and
trust its current hash before acceptance testing.
