# GPT-5.6 Model Router Skills

Version 0.2.2 is a self-contained Codex marketplace for explicitly routing
work autonomously to GPT-5.6 Luna, Terra, and Sol roles. It keeps the root task's
model unchanged. Routing is explicit at the root, then may be re-entered only
by a child that received a bounded delegation capability.

The plugin provides four local contracts:

- ten model-pinned, schema-2 custom-agent templates;
- structured route decisions with risk floors and review requirements;
- a complexity-triggered local task-graph ledger for multi-wave orchestration; and
- explicit, reversible setup for custom agents and depth-two recursion.

It has no hooks, MCP servers, connectors, credentials, or implicit invocation.

Public information: [product page](https://paxdynamics.com/plugins/gpt-5-6-model-router),
[support](https://paxdynamics.com/plugins/gpt-5-6-model-router/support),
[privacy](https://paxdynamics.com/plugins/gpt-5-6-model-router/privacy), and
[terms](https://paxdynamics.com/plugins/gpt-5-6-model-router/terms).

## Install from GitHub

Add this repository as a Codex marketplace, then install the plugin:

```bash
codex plugin marketplace add pax-k/gpt-5.6-model-router-skills
codex plugin add gpt-5-6-model-router@gpt-5-6-model-router-skills
```

Release archives and checksums are published on the
[GitHub releases page](https://github.com/pax-k/gpt-5.6-model-router-skills/releases).

## Install locally

From this repository:

```bash
codex plugin marketplace add "$(pwd)"
codex plugin add gpt-5-6-model-router --marketplace gpt-5-6-model-router-skills
```

Refresh ChatGPT desktop, start a new task, then install and verify the managed
agent files:

```text
$setup-gpt56-model-router Install and verify the model router agents.
```

Setup writes only the ten `gpt56-router-*.toml` files under
`~/.codex/agents/`. To allow the one bounded descendant layer used by the
workflow contract, explicitly request recursion setup as well:

```text
$setup-gpt56-model-router Enable and verify bounded depth-two routing.
```

Start a new task after either setup action. Then invoke routing explicitly:

```text
$route-gpt56-task Complete this request autonomously through the best GPT-5.6 routes.
```

## What is implemented

Version 0.2.2 implements the routing policy, protocol schemas, 25 workflow
scenarios, task-graph orchestration, route-message construction, runtime
evidence inspection, and explicit recursion setup documented in the bundled
references. `references/model-effort-research.md` remains evidence and
calibration guidance, not a promise that every API-supported model/effort pair
is a default route.

The supported production roles are:

| Role | Model / effort | Primary use |
| --- | --- | --- |
| `gpt56_router_luna_worker` | Luna / low | Mechanical, strongly verified work |
| `gpt56_router_terra_explorer` | Terra / medium | Read-only exploration and evidence gathering |
| `gpt56_router_terra_worker` | Terra / medium | Bounded everyday implementation |
| `gpt56_router_sol_engineer` | Sol / medium | Ambiguous or architectural implementation |
| `gpt56_router_sol_debugger` | Sol / high | Difficult debugging and risky repair |
| `gpt56_router_sol_reviewer` | Sol / high | Independent consequential review |
| `gpt56_router_terra_investigator` | Terra / high | Broad competing-hypothesis investigation |
| `gpt56_router_sol_specialist_xhigh` | Sol / xhigh | Dense proof obligations after evidence-backed escalation |
| `gpt56_router_sol_specialist_max` | Sol / max | Rare bounded frontier work after xhigh failure or explicit quality-first authority |
| `gpt56_router_sol_advisor` | Sol / medium | Read-only synthesis or human-decision support |

`xhigh` and `max` are escalation routes, not automatic retries or generic
defaults. A route decision records the reason, risk floor, validation plan,
review requirement, and applicable authority boundary.

## Root envelope and re-entry

The user explicitly invokes the router at the root. That invocation may create
a root envelope with a goal, authority limits, and budgets. Re-entry by a child
is allowed only when its received capability explicitly permits it. A role name
does not by itself grant delegation authority.

The default envelope is autonomous within the requested scope:

- in-scope work continues across waves without router-authored previews,
  permission checks, or approval pauses;
- agents make and record ordinary semantic, product, and implementation choices
  using the best evidence-backed reversible option;
- external, destructive, credentialed, and costly actions follow the authority
  recorded in the root task profile; only an actual host/tool confirmation may
  pause them;
- maximum routing depth is two (root -> authorized workstream owner -> leaf);
- children, parallelism, allowed roles/models, write scopes, and forbidden
  actions are bounded per capability; and
- all roles except Terra explorer and Sol engineer are always leaves. Those two
  roles may own a bounded workstream only when the root supplies a valid
  delegation capability.

When a child exhausts a budget, finds new work, or encounters a blocker, it
returns a structured event upward. Ordinary semantic decisions are made and
recorded autonomously. Only the root can
complete the user's overall request.

## Runtime routing and proof

Before spawning, inspect the callable `spawn_agent` schema in the current
task. The router selects exactly one enforceable mode:

- **custom-agent:** use `agent_type`; the installed TOML supplies the role,
  pinned model/effort, instructions, and declared defaults;
- **model-override:** when `agent_type` is unavailable but `model` and
  `reasoning_effort` are exposed, use those fields with `fork_turns: "none"`
  and include the selected bundled role instructions in the child message;
- **unsupported:** if neither contract is present, stop before spawning. Never
  put a role into `task_name` or silently inherit the root model.

The task profile may record `current_sandbox` and host evidence for
`read_only_agent_sandbox_enforced`, but these fields are observational rather
than routing gates. Live parent permissions may override a custom agent's TOML
sandbox default. Explorer, reviewer, and advisor roles still run under the
parent task's effective permissions and follow their read-only role contract.
Use `inspect_spawn.py --expected-sandbox` only when strict sandbox isolation is
an explicit acceptance requirement.

Evidence is intentionally tiered:

| Proof tier | What it proves | What it does not prove |
| --- | --- | --- |
| Automated repository proof | Fixtures, schema checks, decisions, message construction, and inspector parsing behave as tested | A real hosted runtime accepted or applied a route |
| Local setup proof | The local templates/config were installed, enabled, checked, or rolled back exactly | A future task or desktop build exposes compatible spawn fields |
| Live runtime proof | Persisted child metadata matches the selected role/mode, model, and effort for that actual spawn | General compatibility across accounts, clients, or later releases |

Use the returned spawn identifier and the inspector's persisted-rollout bridge
when the runtime supplies one. Do not treat child self-report as route proof.
If no bridge is available, report live proof as unavailable rather than
claiming success.

## Local CLIs

The structured router accepts a task profile from a file or standard input:

```bash
ROUTER="plugins/gpt-5-6-model-router/skills/route-gpt56-task"
python3 "$ROUTER/scripts/route_task.py" decide --input task-profile.json --json
python3 "$ROUTER/scripts/orchestrate.py" init --input task-profile.json --ledger .router-ledger.json --json
python3 "$ROUTER/scripts/orchestrate.py" ready --ledger .router-ledger.json --json
python3 "$ROUTER/scripts/orchestrate.py" dispatch --ledger .router-ledger.json --json
python3 "$ROUTER/scripts/orchestrate.py" apply-event --ledger .router-ledger.json --event child-event.json --json
python3 "$ROUTER/scripts/orchestrate.py" control --ledger .router-ledger.json --control human-control.json --json
python3 "$ROUTER/scripts/orchestrate.py" status --ledger .router-ledger.json --json
python3 "$ROUTER/scripts/orchestrate.py" complete-check --ledger .router-ledger.json --json
```

These CLIs always return JSON. `ready` previews a concurrency-safe wave;
`dispatch` atomically reserves it and must run before spawning so repeated
reads cannot duplicate work. `control` applies root-only pause, resume,
cancel, redirection, scope, decision, and blocker transitions. Simple one-wave work remains task-local. When
recursion, a second wave, more than three nodes, pause/block, or explicit
resumability triggers persistence, the router atomically creates
`.codex/gpt56-router/<task-id>.json`. An explicit `--ledger` path remains
available and makes durability failure blocking. The older
`route_task.py --kind` interface is not a v0.2 contract.

Custom-agent setup remains deliberately narrow:

```bash
SETUP="plugins/gpt-5-6-model-router/skills/setup-gpt56-model-router"
python3 "$SETUP/scripts/manage_agents.py" check --json
python3 "$SETUP/scripts/manage_agents.py" install --json
python3 "$SETUP/scripts/manage_agents.py" uninstall --json
python3 "$SETUP/scripts/manage_recursion.py" check --json
python3 "$SETUP/scripts/manage_recursion.py" enable --json
python3 "$SETUP/scripts/manage_recursion.py" disable --json
```

Agent installation refuses divergent user-owned destinations by default.
`install --force` is the only replacement path and creates backups first under
`~/.codex/.gpt56-router-agent-backups/`, outside agent discovery.
Uninstall likewise removes only byte-identical managed files by default;
`uninstall --force` backs up divergent managed files before removing them.
Recursion enablement is likewise explicit, verified, and reversible; it does
not silently rewrite global configuration.

## Verify the repository

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py
python3 scripts/validate_publication.py
python3 scripts/build_publication.py
```

The repository validator uses only the Python standard library. It validates
the marketplace/manifest contract, both explicitly invoked skills, and all ten
schema-2 agent templates. The test suite exercises the 25 versioned workflow
fixtures and distinguishes fixture-based automated proof from live runtime
proof.

Model availability and the callable spawn schema can still vary by account,
workspace policy, client, and task runtime. Route incompatibility or an
unavailable pinned model is reported; it is never silently substituted.

## Publishing

The `submission/` directory contains the reviewer listing, starter prompts,
exactly five positive and three negative test cases, release notes, availability
choice, and policy attestations. `scripts/build_publication.py` creates a
deterministic, sanitized skills-only archive under `dist/` and prints its
SHA-256 checksum. Local runtime evidence and machine-specific artifacts are not
included in the public bundle.
