# Governed routing policy v0.4

Governance activates only for a turn whose user prompt explicitly contains
`$route-gpt56-task`. Non-router turns and their delegation remain unaffected.

The root owns the outcome and may execute directly. On an active router turn,
every root or delegated workstream must first register one schema-v4 intent.
Ordinary route recommendations are advisory, but a different route requires an
accountable override. Structural protocol, authority, ownership, critical
floor, and critical-review rules are enforced by trusted plugin hooks.

## Default frontier

| Work | Preferred route | Policy |
| --- | --- | --- |
| Clear, narrow, strongly verified mechanical work | Luna/low worker | Advisory |
| Ordinary implementation | Terra/medium worker | Advisory |
| Ordinary read-only exploration | Terra/medium explorer | Advisory |
| Broad evidence search with competing hypotheses | Terra/high investigator | Advisory |
| Ambiguous, architectural, cross-layer, or critical implementation | Sol/medium engineer | Critical floor when applicable |
| Difficult debugging or weakly verified critical risk | Sol/high debugger | Critical floor when applicable |
| Independent critical review | Separate Sol/high reviewer | Required when applicable |
| Read-only architecture advice | Sol/medium advisor | Advisory |
| Recorded lower-route failure | Sol/xhigh specialist | Privileged authority required |
| Hardest quality-first or repeated failure | Sol/max specialist | Privileged authority required |

Model family follows ambiguity, judgment, and risk. Effort follows exploration
and verification depth. Context breadth alone does not select Sol. See
`model-effort-research.md` for the evidence and ignored combinations.

## Authority

An ordinary noncritical recommendation override may use root authority, but it
must record a reason code, rationale, and non-empty reference.

The following require `user`, `task_contract`, or `recorded_failure` authority
and a non-empty reference:

- `quality_first`;
- Sol/xhigh or Sol/max;
- execution below the critical Sol/medium floor;
- critical root-direct execution when runtime evidence cannot prove root
  effort;
- skipping the required critical review.

User and task-contract authority are escape hatches, not implicit permission.

## Delegation

- `fork_turns: "none"` is the default.
- A positive bounded fork needs a recorded rationale.
- `fork_turns: "all"` is valid only for inherited-root execution with an
  accountable override. It cannot include custom role, model, or effort fields.
- Children are leaves unless their intent grants exactly `one-level`.
- Depth-two descendants must receive `Delegation grant: none`.
- Disjoint writers may overlap. Live writers with equal, ancestor, or
  descendant owned paths serialize.
- Children have no commit, tag, or push authority by default.

Use the `spawn_request` emitted by `route_guard.py prepare` exactly. The
`PreToolUse` hook rejects malformed, modified, reused, sensitive, or
unauthorized `Agent` calls before runtime.

## Critical review

Critical domains include security, authentication, authorization, secrets,
credentials, payments, financial mutations, destructive migrations,
concurrency, distributed state, and safety.

After critical execution converges:

1. Snapshot its owned paths with `route_guard.py snapshot`.
2. Register a separate Sol/high reviewer intent with the source intent ID and
   manifest SHA-256.
3. Require the reviewer to return the machine-readable `Router-Review` footer.
4. Re-snapshot after any subsequent change. A changed manifest invalidates the
   earlier review.

Missing or stale required review blocks closeout. Unavailable audit metadata
produces a visible warning; it is not misrepresented as proof.

## Evidence and privacy

State lives below `PLUGIN_DATA/governor`, keyed by session and turn, and is
atomically lock-protected. It stores hashes, route metadata, reason codes,
decisions, timestamps, runtime identity fields, manifests, and outcomes.

It does not store raw prompts, objectives, references, messages, tool output,
diffs, logs, or detected secrets. Completed state is retained for no more than
30 days or 1,000 completed turns.

Hook-derived sandbox and command evidence is observational. Children inherit
the active runtime sandbox and approval state; hooks are guardrails and do not
create an adversarial isolation boundary.
