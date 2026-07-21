# Advisory routing policy v0.3

The root decides whether delegation is worthwhile and may override every recommendation. These defaults optimize for best expected value, not protocol compliance.

| Work | Preferred route |
| --- | --- |
| Clear, narrow, strongly verified mechanical work | Luna / low |
| Ordinary implementation | Terra / medium worker |
| Ordinary read-only exploration | Terra / medium explorer |
| Broad investigation with competing hypotheses | Terra / high investigator |
| Ambiguous, architectural, broad, or critical implementation | Sol / medium engineer |
| Difficult debugging or weakly verified critical risk | Sol / high debugger |
| Independent critical review | Sol / high reviewer |
| Read-only architecture advice | Sol / medium advisor |

Recorded failure suggests Luna/low → Terra/medium → Sol/medium → Sol/high → Sol/xhigh → Sol/max. `quality_first` suggests Sol/max. The root may skip, reverse, or stop escalation when evidence, cost, or availability warrants it. Ultra is not bundled.

Critical domains include security, authentication, authorization, secrets, credentials, payments, financial mutations, destructive migrations, concurrency, distributed state, and safety. Independent Sol/high review is recommended for them, never mandatory.

`route_task.py recommend` returns the preferred route even when unavailable. `availability` is `custom_agent`, `model_override`, `unavailable`, or `unknown`; none of these values blocks root execution. Reason codes explain the helper output for evaluation without becoming production paperwork.

Routed handoffs use `fork_turns: "none"` by default and may use a positive turn count when bounded copied context has higher expected value. A full-history `fork_turns: "all"` spawn inherits the parent route, must omit `agent_type`, `model`, and `reasoning_effort`, and therefore remains outside the routed-handoff helper. Children remain leaves unless the root gives the exact one-level grant. Independent work may overlap; overlapping writers normally serialize.
