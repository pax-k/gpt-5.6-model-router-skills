# OpenAI plugin submission package

This directory is the reviewer-facing source of truth for the skills-only
submission of GPT-5.6 Model Router v0.2.0.

- `portal-fields.json` contains the exact listing fields and starter prompts.
- `reviewer-tests.json` contains exactly five positive and three negative cases.
- `release-notes.md` contains reviewer and release copy.
- `policy-attestations.md` records the factual submission attestations.
- `availability.md` records the recommended country selection.
- `clean-room-checklist.md` is the release gate.

Build and validate the upload archive from the repository root:

```bash
python3 scripts/validate_publication.py
python3 scripts/build_publication.py
```

The build script packages only the plugin directory. Repository-only tests,
private runtime artifacts, caches, and machine-specific identifiers are not
included.
