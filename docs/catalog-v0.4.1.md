# GPT-5.6 Model Router v0.4.1 catalog contraction

Status: implemented candidate

## Decision

The custom-agent catalog contains eight semantic roles on five model/effort
combinations:

| Combination | Roles |
| --- | --- |
| Luna/high | mechanical worker |
| Terra/medium | explorer, worker |
| Terra/high | investigator |
| Sol/medium | engineer, advisor |
| Sol/high | debugger, reviewer |

Luna/low is replaced by Luna/high. Sol/xhigh and Sol/max custom agents are
retired. Quality-first work and recorded Sol-level failures are absorbed into
the Sol/high debugger role.

The root may use any model and reasoning effort. The Sol/medium critical floor
applies only to delegated critical execution; critical root-direct execution
still requires manifest-bound independent Sol/high review.

Trusted hooks govern every root `Agent` spawn, not only explicit router turns.
The root must register a schema-v4 intent through `route_guard.py prepare` and
use its exact request. Recommendations are enforced defaults; only user,
task-contract, or recorded-failure authority can select another route.
Ordinary root-only work remains unrestricted.

The catalog runs at effective depth one. Every routed child is a leaf, the v4
intent accepts only `delegation_grant: "none"`, and the installer contracts
intact router-owned depth-two state while retaining the original value for
uninstall restoration.

## Failure semantics

A failed route may escalate from Luna/high to Terra/medium, from Terra to
Sol/medium, and from Sol/medium to Sol/high. A recorded Sol/high failure does
not select a higher effort. It requires a materially revised plan, narrower
decomposition, or stronger verifier evidence before retrying at Sol/high.

The public schema continues to recognize all runtime effort strings in
historical failure evidence. A selected route remains valid only when it
matches a bundled role, so xhigh and max cannot be dispatched.

## Upgrade behavior

Transactional setup installs eight templates. It recognizes the v0.4.0
Luna/low schema-5 template as an owned predecessor and upgrades it after
backup. It also backs up and removes byte-identical retired Sol/xhigh and
Sol/max templates from earlier releases.

A modified retired template is preserved and causes setup to fail with a
repair instruction unless the user explicitly runs `install --force`. This
prevents silent deletion of user-owned changes while ensuring a successful
upgrade cannot leave stale router roles discoverable.

## Release boundary

The published `v0.4.0` tag and archive remain immutable. This change is carried
as the `0.4.1+codex.*` candidate and requires its own validation and release
gate before publication.
