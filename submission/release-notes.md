# GPT-5.6 Model Router v0.4.1

This release contracts the governed routing catalog while preserving the v0.4
protocol and critical-review guarantees.

- Trusted hooks establish lightweight state on every turn and deny every
  unprepared root `Agent` spawn, including on non-explicit turns. Ordinary
  root-only work remains unaffected.
- Three clean-break schema-v4 contracts separate task facts, pure recommendations, and execution authority.
- Trusted bundled hooks deny malformed or unmatched Agent calls before runtime, enforce bounded delegation and disjoint writer ownership, and retain only hashes and route metadata under `PLUGIN_DATA`.
- Recommended routes are enforced defaults. Deviations require user,
  task-contract, or recorded-failure authority. Critical work has a Sol/medium
  floor and requires separate hash-bound Sol/high review unless explicit
  authority records an exception.
- Eight schema-v5 custom roles implement Luna/high, Terra/medium-high, and
  Sol/medium-high.
- Sol/xhigh and Sol/max are retired. Quality-first work and recorded Sol-level
  failures are absorbed into the Sol/high debugger with replanning required at
  the ceiling.
- Root-direct work remains valid; only explicit router turns require a
  root-direct intent at closeout. Full-history inheritance is limited to
  explicitly recorded inherited-root execution without custom role or model
  fields.
- The router never constrains the root model or root reasoning effort.
  Delegated critical work retains the Sol/medium floor, and critical
  root-direct work retains independent Sol/high review.
- Transactional setup verifies Python 3.9+, stable hooks, and stable multi-agent
  support, installs the role catalog, and enforces effective depth one.
  Router-owned depth-two state is contracted while preserving uninstall
  restoration. Hook trust remains a manual `/hooks` action.
- Reproducible packaging uses tag-derived `SOURCE_DATE_EPOCH`, retains bundled hooks and dependency licenses, and emits a SHA-256 sidecar.

The installer upgrades the prior Luna/low schema-5 template and removes
untouched retired specialist templates after backup. Schema-v3 inputs still
receive an explicit v0.4 migration error. A hook-free or hooks-stripped portal
package is not an acceptable substitute.
