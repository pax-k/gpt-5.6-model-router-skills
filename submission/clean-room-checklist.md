# Clean-room release checklist

- [x] Repository unit suite passes.
- [x] Repository and official skill/plugin validators pass.
- [x] Publication validator passes.
- [x] Deterministic archive builds and its SHA-256 is recorded.
- [x] Archive contains only the plugin root and approved runtime files.
- [x] Archive contains no caches, bytecode, private evidence, absolute local
      paths, secrets, or persisted thread identifiers.
- [x] Public Git marketplace install, agent check, recursion check, and
      byte-identical manifest verification pass.
- [x] Public website, support, privacy, terms, repository, and release URLs load.
- [x] Submission source contains exactly five positive and three negative test
      cases.
- [ ] Skills-only bundle is submitted from an identity-verified developer account
      with Apps Management write access.
