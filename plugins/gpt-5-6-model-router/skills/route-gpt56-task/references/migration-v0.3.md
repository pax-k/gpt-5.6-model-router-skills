# Migrating to autonomy-first v0.3

Version 0.3 is unpublished and intentionally breaks the earlier candidate contract. The public historical release remains at tag `v0.2.2`.

Removed from production behavior:

- mandatory task profiles, script calls, exact-role compliance, and fail-closed unavailable routes;
- fixed empty forks, mandatory leaf-only fan-out, required critical review, and fixed repair waves;
- routing calculations in normal user updates.

Optional evaluation tooling now uses task-profile and route-recommendation schema v3. Run `route_task.py recommend`; its output is advisory and never blocks root execution. `build_spawn_prompt.py` accepts a root-selected bundled route, empty or positive bounded forks, and `Delegation grant: none | one-level`. Full-history forks inherit the parent route and must be created directly without routing fields.

The ten role names remain stable and templates move to schema 4. Without the exact one-level grant they remain leaves. A granted child may create bounded descendants, but every descendant receives `Delegation grant: none`.

Use one transactional setup command:

```bash
python3 <setup-skill-directory>/scripts/setup_router.py install --json
```

It upgrades byte-identical schema-2 or schema-3 templates after backup, adopts trusted legacy router depth state, and ensures effective depth is at least 2. Modified templates require `--force`; user-modified managed depth is never overwritten. After installation, restart Codex and run the canaries in `runtime-evidence.md`.
