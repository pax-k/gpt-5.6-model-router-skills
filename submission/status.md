# Submission status

Updated: July 21, 2026

Version `v0.3.0` is the public autonomy-first GitHub release, built from plugin version `0.3.0+codex.20260721090607`. The public `v0.2.2` tag remains the historical orchestration release. The external plugin-portal submission remains separately gated and has not been submitted.

Local candidate verification:

- 59 repository tests pass.
- Repository, publication, both official skill, and official plugin validators pass.
- Deterministic archive: `dist/gpt-5-6-model-router-0.3.0.zip`.
- SHA-256: `8dbbd4c08eda76e7b398787bbb0efb1e3d2492be188ab43778b97bfe1fe8d61c`.

Live plugin discovery passed for both explicit skills at the exact release version. Schema-4 acceptance produced a Terra/medium depth-1 parent, Luna/low depth-2 leaf, and separate Luna/low no-grant leaf with persisted parent chains and `fork_turns: "none"`. Sandbox was observed only, not asserted.
