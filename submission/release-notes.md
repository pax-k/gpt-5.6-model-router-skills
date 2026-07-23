# GPT-5.6 Model Router v0.4.0

This release adds governed, explicitly activated routing while preserving root autonomy for ordinary work.

- Exact `$route-gpt56-task` invocation activates local governed state; unrelated Agent use remains untouched.
- Three clean-break schema-v4 contracts separate task facts, pure recommendations, and execution authority.
- Trusted bundled hooks deny malformed or unmatched Agent calls before runtime, enforce bounded delegation and disjoint writer ownership, and retain only hashes and route metadata under `PLUGIN_DATA`.
- Ordinary route choices remain advisory with accountable override evidence. Critical work has a Sol/medium floor and requires separate hash-bound Sol/high review unless explicit authority records an exception.
- Ten schema-v5 custom roles implement the curated Luna/low, Terra/medium-high, and Sol/medium-high-xhigh-max catalog.
- Root-direct work remains valid but must register an intent. Full-history inheritance is limited to explicitly recorded inherited-root execution without custom role or model fields.
- Transactional setup verifies Python 3.9+, stable hooks, and stable multi-agent support, installs the role catalog, and enables effective depth two. Hook trust remains a manual `/hooks` action.
- Reproducible packaging uses tag-derived `SOURCE_DATE_EPOCH`, retains bundled hooks and dependency licenses, and emits a SHA-256 sidecar.

Schema-v3 inputs receive an explicit v0.4 migration error. A hook-free or hooks-stripped portal package is not an acceptable substitute.
