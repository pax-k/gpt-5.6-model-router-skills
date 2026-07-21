# Clean-room release checklist

- [x] Full repository suite passes after autonomy-first changes.
- [x] Repository, publication, official skill, and official plugin validators pass after autonomy-first changes.
- [x] Deterministic v0.3.0 archive and SHA-256 are refreshed.
- [x] Archive excludes caches, private evidence, local paths, secrets, and persisted task identifiers.
- [x] Submission source contains exactly seven positive and one negative cases.
- [x] Codex `plugin/read` reports both explicit skills enabled at the exact installed candidate version.
- [x] Live canaries verify schema 4, depth at least 2, one-level descendant behavior, default-leaf behavior, persisted parent chains, and fork provenance.
- [x] GitHub publication, tag, and push received explicit release authorization.
- [ ] External plugin-portal submission receives separate legal-attestation authorization.
