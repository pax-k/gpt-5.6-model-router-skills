---
name: route-gpt56-task
description: Explicitly activate autonomy-first GPT-5.6 routing for a task, with cost-aware model defaults, optional compact delegation, bounded descendant grants, and advisory critical review.
---

# Route GPT-5.6 work autonomously

This skill activates only when explicitly invoked. Once active, use autonomous routing judgment for the whole task. The root owns the result and may handle work itself, delegate one or more useful workstreams, and may override every role, effort, fork, and review default or change course when live evidence warrants it.

Optimize for best expected value: prefer the cheapest adequate execution unless stronger reasoning or parallelism has a meaningful quality or latency benefit. User instructions and runtime or security policy remain authoritative.

## Decide whether delegation helps

Keep work at the root when delegation overhead exceeds its benefit. Delegate when a bounded handoff improves speed, quality, context isolation, or independent verification. Independent work may run concurrently. Writers with overlapping or uncertain ownership normally serialize; disjoint writers may overlap.

Use these as defaults, not requirements:

- Luna/low for clear mechanical work.
- Terra/medium for ordinary implementation or exploration; Terra/high for broad investigation.
- Sol for ambiguity, architecture, debugging, critical risk, review, or escalation.
- `fork_turns: "none"` with compact path-based context.
- Independent Sol/high review for critical work.

The root may override any default based on task evidence, runtime availability, cost, latency, or user priorities. An unavailable preferred route never blocks the task; handle it at the root or choose any available fallback.

## Delegate compactly

Send objective, canonical references, owned paths, essential constraints, and focused verification. Do not paste source files, diffs, logs, the parent conversation, `AGENTS.md`, or repository documentation unless direct context is genuinely more valuable than a path-based handoff.

Children are leaves by default. Include the exact line `Delegation grant: one-level` only when a child can usefully create bounded descendants. That child must give every descendant `Delegation grant: none`; descendants cannot delegate further. Open recursion is out of scope.

Prefer concise action updates only when agents start, materially escalate, hit blockers, or return important findings. Do not expose route scores or routing paperwork by default.

## Review while value remains

Critical work normally receives independent Sol/high review, but the root retains override authority. Repair and review cycles have no fixed count: continue only while another cycle has positive expected value. Run focused verification in workstreams and the appropriate integrated gate after changes converge.

## Optional helpers

Production routing does not require schemas or scripts. For evaluation or troubleshooting only:

```bash
python3 <skill-directory>/scripts/route_task.py recommend --input task-profile.json --json
python3 <skill-directory>/scripts/build_spawn_prompt.py --input handoff.json --json
```

The first emits advisory schema v3 and never orders delegation. The second validates compact routed handoffs, accepts any bundled `selected_route`, defaults to an empty fork, permits positive bounded forks, rejects full-history forks that would inherit the parent route, and supports `Delegation grant: none` or `one-level`. The root may bypass either helper.

See `references/routing-policy.md` for advisory defaults and `references/runtime-evidence.md` for install-time canaries.
