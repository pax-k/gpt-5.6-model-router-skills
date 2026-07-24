# Governed routing policy v0.4.1

Once plugin hooks are trusted, every root `Agent` spawn is governed, whether or
not the prompt explicitly contains `$route-gpt56-task`. Ordinary root-direct
turns remain unaffected and need no route intent.

The root owns the outcome and may execute directly on any model or effort.
Every delegated workstream must first register one schema-v4 intent and use the
exact emitted request. The recommended route is enforced. A different route
requires privileged authority. Explicit router turns also register root-direct
work before closeout.

## Default frontier

| Work | Preferred route | Policy |
| --- | --- | --- |
| Clear, narrow, strongly verified mechanical work | Luna/high worker | Enforced default |
| Ordinary implementation | Terra/medium worker | Enforced default |
| Ordinary read-only exploration | Terra/medium explorer | Enforced default |
| Broad evidence search with competing hypotheses | Terra/high investigator | Enforced default |
| Ambiguous, architectural, cross-layer, or critical implementation | Sol/medium engineer | Critical floor when applicable |
| Difficult implementation, debugging, quality-first work, or weakly verified critical risk | Sol/high debugger | Critical floor when applicable |
| Independent critical review | Separate Sol/high reviewer | Required when applicable |
| Read-only architecture advice | Sol/medium advisor | Enforced default |
| Recorded Sol/medium or Sol/high failure | Replan with Sol/high debugger | No higher custom-agent effort |

Model family follows ambiguity, judgment, and risk. Effort follows exploration
and verification depth. Context breadth alone does not select Sol. See
`model-effort-research.md` for the evidence and ignored combinations.

## Authority

The following require `user`, `task_contract`, or `recorded_failure` authority
and a non-empty reference:

- selecting any route other than the recommendation;
- selecting a fallback when the preferred route is unavailable;
- `quality_first`;
- execution below the critical Sol/medium floor;
- skipping the required critical review.

User and task-contract authority are escape hatches, not implicit permission.
The custom-agent ceiling is Sol/high. Recorded failure changes the plan,
evidence, or work decomposition; it does not select xhigh or max.

The root model and root effort are unrestricted, including for critical
root-direct execution. The delegated critical floor does not apply to the root.
Critical root-direct work remains subject to the same manifest-bound
independent Sol/high review at closeout.

## Delegation

- `fork_turns: "none"` is the default.
- A positive bounded fork needs a recorded rationale.
- `fork_turns: "all"` is valid only for inherited-root execution with an
  accountable override. It cannot include custom role, model, or effort fields.
- Effective depth is exactly one.
- Every child intent uses `Delegation grant: none`; children cannot delegate.
- Disjoint writers may overlap. Live writers with equal, ancestor, or
  overlapping owned paths serialize.
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
