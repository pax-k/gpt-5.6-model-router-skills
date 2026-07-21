# OpenAI plugin submission package

Reviewer-facing source for the skills-only GPT-5.6 Model Router v0.3.0 candidate.

`portal-fields.json` contains listing copy, `reviewer-tests.json` contains seven positive and one negative acceptance cases, and the remaining documents record release, policy, availability, and clean-room gates.

```bash
python3 scripts/validate_publication.py
python3 scripts/build_publication.py
```

The deterministic archive contains only the plugin directory. Publishing and portal submission require a separate explicit request.
