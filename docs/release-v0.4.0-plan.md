# GPT-5.6 Model Router v0.4.0 implementation and release plan

Status: implementation in progress
Branch: `codex/release-v0.4.0`
Updated: 2026-07-23

## Outcome

Release a governed router that preserves root autonomy while enforcing
protocol, authority, critical-review, and evidence invariants only on turns
that explicitly contain `$route-gpt56-task`.

The release is complete when:

- no protocol-invalid routed `Agent` spawn reaches runtime;
- critical work has the Sol/medium execution floor and a current,
  manifest-bound independent Sol/high review unless privileged authority
  records an exception;
- persisted evidence records actual role, model, effort, fork, parent, and
  outcome without raw prompts, messages, tool output, diffs, or secrets;
- non-router turns are unaffected;
- Python 3.9 and current-stable validation pass;
- the GitHub release is reproducible and the identical hook-bearing archive is
  accepted by the portal draft.

## Accepted decisions

- Schema v4 is a clean break. Schema-v3 payloads fail with a migration error.
- Role-template schema moves to v5.
- The ten-role model/effort catalog is retained. Terra/low remains
  experimental; see
  `plugins/gpt-5-6-model-router/skills/route-gpt56-task/references/model-effort-research.md`.
- Model family follows ambiguity, judgment, and risk. Effort follows
  exploration and verification depth.
- Critical execution has a Sol/medium floor and a separate Sol/high review.
- `quality_first`, `xhigh`, and `max` require `user`, `task_contract`, or
  `recorded_failure` authority with a reference.
- Root-direct execution is valid but must register a root intent on an active
  router turn.
- There is no total-agent or Luna quota.
- Writers with overlapping owned paths serialize.
- Children have no commit, tag, or push authority by default.
- Hooks are enforceable guardrails once trusted, not an adversarial isolation
  boundary.
- The portal receives no weakened skills-only edition.

## Work plan

### 1. Contracts and pure policy

- [x] Define `task-profile-v4`.
- [x] Define `route-recommendation-v4`.
- [x] Define `route-intent-v4`.
- [x] Replace boolean quality-first with authority-bearing `quality_mode`.
- [x] Encode the accepted family/effort selection axes and narrow Terra/high.
- [x] Add valid and invalid contract fixtures, including explicit v3 rejection.

### 2. Governed hook runtime

- [x] Add `route_guard.py` with `prepare`, `snapshot`, `audit`, and `status`.
- [x] Add `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SubagentStart`,
  `SubagentStop`, and `Stop` hook entries.
- [x] Validate exact event inputs and supported output shapes against current
  Codex hook documentation.
- [x] Prove inactive turns return no policy output.
- [x] Deny malformed/missing intents, task reuse, unavailable routes without
  acknowledgement, unauthorized nested delegation, unauthorized escalation,
  full-history custom routes, overlapping writers, and sensitive handoffs.
- [x] Complete atomic locking, retention, and privacy tests.
- [x] Complete critical manifest snapshot, reviewer footer, and stale-review
  invalidation tests.
- [x] Complete child commit-command checks and post-HEAD observation logic.

### 3. Setup, roles, and documentation

- [x] Move role templates to schema v5 and add machine-readable result footers.
- [x] Vendor the Python 3.9 TOML compatibility implementation and license.
- [x] Complete transactional schema-v2/v3/v4 role migration.
- [x] Verify hooks and multi-agent features without auto-trusting hooks.
- [x] Document `/hooks` review/trust, inherited sandbox limitations, escape
  authority, persisted evidence, and failure behavior.
- [x] Update README, skill instructions, migration guide, listing copy, and
  submission fields.

### 4. Validation and CI

- [x] Add Python 3.9 and current-stable GitHub Actions jobs.
- [x] Add hook-event fixtures for router and non-router activation.
- [x] Cover root, Luna, Terra, Sol, model override, and inherited execution.
- [x] Cover critical floor/review, authorized exceptions, stale hashes,
  nested grants, ownership collision, privacy, missing metadata, and
  concurrent state writes.
- [x] Add package hygiene, deterministic archive, and clean-worktree checks.
- [x] Run all tests under Python 3.9 and current stable (78 tests on each).

### 5. Acceptance and release

- [x] Install `0.4.0+codex.20260723152638` without auto-trusting hooks.
- [ ] Confirm hook trust manually.
- [ ] Prove one invalid routed spawn is denied before runtime.
- [ ] Prove valid routes and critical-review binding.
- [ ] Prove persisted identity/model/effort/fork evidence.
- [ ] Prove an unrelated non-router task is unaffected.
- [ ] Merge through a reviewed release PR.
- [ ] Create annotated `v0.4.0`.
- [ ] Build the tag-derived reproducible ZIP and SHA-256 checksum.
- [ ] Publish the GitHub Release.
- [ ] Upload the identical archive to a portal draft.
- [ ] Obtain explicit confirmation before final legal/policy attestations and
  **Submit for Review**.
- [ ] After approval, obtain a second explicit confirmation before public
  directory publication.

## Stop conditions

- Stop the portal leg if the portal rejects, strips, or cannot execute bundled
  hooks. The GitHub release may remain valid.
- Stop before final portal attestations and before public directory
  publication for the required user confirmations.
- Never promote raw transcripts, local paths, rollout IDs, or credentials.
- Preserve and exclude the existing `.tmp/` and `evals/` trees unless an
  individual sanitized fixture is deliberately promoted.

The final archive command is:

```bash
python3 scripts/build_publication.py --release-tag v0.4.0
```

`--release-tag` rejects lightweight or missing tags and derives
`SOURCE_DATE_EPOCH` from the annotated tagger timestamp.

## Validator compatibility note

The current official Codex manual and `plugin.json` specification accept a
top-level `hooks` path, and Codex CLI 0.144.4 reports stable enabled hooks and
loads this local hook-bearing candidate. The bundled plugin-creator validator
still rejects every top-level `hooks` field. Treat that as a stale-validator
compatibility defect: retain hooks, prove the package through the current CLI
and fresh installed-candidate acceptance, and do not weaken the release to
satisfy the older validator.
