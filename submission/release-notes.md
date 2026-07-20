# GPT-5.6 Model Router v0.2.2

This patch closes two orchestration completion gaps found by the engineering
routing evaluation.

- Mandatory review results are accepted only after implementation and from a
  different canonical `agent_path` than the implementer.
- Redirected nodes are marked superseded and no longer block completion, while
  ordinary cancellations remain visible as unmet work.
- Workflow fixtures and regression tests cover self-review rejection,
  independent review success, redirect completion, and cancellation gating.
- The plugin remains skills-only and contains no MCP server, hosted backend,
  connector, credentials, telemetry, or implicit invocation.
