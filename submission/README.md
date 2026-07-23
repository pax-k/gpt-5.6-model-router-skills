# OpenAI plugin submission package

Reviewer-facing source for the hook-bearing GPT-5.6 Model Router v0.4.0 candidate.

`portal-fields.json` contains listing copy and explicit hook disclosure. `reviewer-tests.json` contains exactly five positive and three negative acceptance cases. The remaining documents record release, policy, availability, and clean-room gates.

The portal archive must be byte-identical to the GitHub Release archive. If the portal rejects, strips, or cannot execute the bundled hooks, submission stops; no weakened skills-only edition is published.

```bash
python3 scripts/validate_publication.py
python3 scripts/build_publication.py
```

The deterministic archive contains only the plugin directory. Publishing and portal submission require a separate explicit request.
