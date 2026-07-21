# GPT-5.6 Model Router v0.3.0

This release replaces mandatory deterministic routing with an explicit autonomy-first guidance layer.

- One explicit invocation activates autonomous routing for the task; the root may work directly or delegate useful workstreams.
- Luna, Terra, Sol, empty-fork, writer coordination, escalation, and critical-review choices are defaults the root may override.
- Recommendation schema v3 preserves unavailable preferred routes without blocking execution.
- The compact handoff helper accepts root-selected bundled routes, empty or positive bounded forks, and exact `none` or `one-level` delegation grants; inherited full-history spawns remain outside the routed helper.
- Ten schema-4 roles remain leaves by default; a granted child may create only depth-2 leaves.
- Unified transactional setup installs roles and enables `agents.max_depth = 2`, preserving higher values and unrelated edits.
- Byte-identical schema-2/schema-3 roles and trusted legacy depth state migrate safely after backup.
- Review and repair continue only while expected value justifies another cycle.

The public historical release remains at tag `v0.2.2`.
