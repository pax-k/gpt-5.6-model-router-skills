# v0.2 migration contract

Status: Implemented release migration for plugin version `0.2.0+codex.*`.

## Scope

v0.2 replaces the one-shot, six-role, schema-1 routing surface with a
structured, ten-role, schema-2 workflow contract. It is intentionally a
breaking local-interface change: do not mix old templates, old CLI invocations,
or schema-1 events with the v0.2 scripts.

## Required local refresh

1. Refresh the marketplace/plugin cache so Codex sees the `0.2.0+codex.*`
   cachebuster.
2. Invoke `$setup-gpt56-model-router` and run `manage_agents.py check --json`.
   Install the ten schema-2 templates if the check reports missing files.
3. Start a new Codex task after agent installation.
4. If bounded descendant routing is wanted, explicitly run
   `manage_recursion.py check --json`, then `enable --json`; do not edit global
   configuration by hand.
5. Re-run `check --json` after either setup action. A local check proves local
   state only; it is not live spawn proof.

The manager protects divergent user-owned files. Review its output and use
`install --force` only with explicit authorization; it backs up divergent owned
filenames before replacement.

## Interface changes

| v0.1 surface | v0.2 replacement |
| --- | --- |
| Six `schema=1` TOMLs | Ten `schema=2` TOMLs, including investigator, xhigh, max, and advisor routes |
| `route_task.py --kind <kind> --json` | `route_task.py decide --input <profile-path-or-> --json` |
| Informal spawn instruction | JSON spawn-call builder with capability and runtime-mode checks |
| One-shot child report | One schema-1 terminal child event envelope |
| Manual route/review flagging | Structured decision with risk floors, reasons, and review requirements |
| Documentation-only recursion | Explicit `manage_recursion.py check|enable|disable` |
| One-shot completion | `orchestrate.py` task graph and root-only `complete-check` |
| Repeated read-and-spawn loop | `ready` preview followed by atomic `dispatch` reservation |
| Ad hoc human steering | Root-only `control` envelope for pause/resume/cancel/redirect/resolution |

The old `--kind` CLI and schema-1 managed templates are not compatibility
aliases. A caller must create a valid v0.2 task profile instead of relying on a
label-only route.

## Stable boundaries

The plugin still does not change the root task model, silently substitute an
unavailable model, use implicit skill invocation, install hooks/MCP/connectors,
or grant authority merely because a role is installed. Custom-agent mode remains
preferred when `agent_type` exists; model-override mode requires `model` and
`reasoning_effort` with `fork_turns: "none"` and does not claim TOML/sandbox
application.

## Rollback

Disable bounded recursion through `manage_recursion.py disable --json`. Remove
only plugin-owned agent files through `manage_agents.py uninstall --json`.
Neither action removes backups or unrelated user configuration. Rollback does
not remove a persisted orchestration ledger; preserve it as evidence unless the
user explicitly requests its removal.

If `config.toml` changed after recursion enablement, `check` may still confirm
that the owned marker and `max_depth = 2` are intact while reporting guarded
rollback. `disable` then refuses an ambiguous full-snapshot restore so it cannot
erase later user edits.

If a managed agent file diverged after installation, use `uninstall --force`
only with explicit authorization; it creates a backup before removal.
