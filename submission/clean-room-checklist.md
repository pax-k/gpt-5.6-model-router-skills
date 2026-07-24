# Clean-room release checklist

- [ ] Full repository suite passes on Python 3.9 and current stable.
- [ ] Repository, publication, official skill, and official plugin validators pass.
- [ ] Reproducible v0.4.1 archive and SHA-256 are built from the annotated tag epoch.
- [ ] Archive excludes caches, private evidence, local paths, secrets, and persisted task identifiers.
- [x] Submission source contains exactly five positive and three negative cases.
- [ ] Fresh installation reports both explicit skills and bundled hooks at the exact candidate version.
- [ ] User trusts the candidate hooks through `/hooks`; installation never performs trust automatically.
- [ ] Live acceptance proves a pre-runtime denial, valid routes, hash-bound critical review, persisted identity/model/effort/fork evidence, and an unaffected non-router task.
- [ ] Reviewed release PR is merged and the annotated `v0.4.1` tag is published.
- [ ] External plugin-portal submission receives separate legal-attestation authorization.
- [ ] Public directory publication receives a final separate confirmation after OpenAI approval.
