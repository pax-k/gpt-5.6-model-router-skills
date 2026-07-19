# Clean-room release checklist

- [ ] Repository unit suite passes.
- [ ] Repository and official skill/plugin validators pass.
- [ ] Publication validator passes.
- [ ] Deterministic archive builds and its SHA-256 is recorded.
- [ ] Archive contains only the plugin root and approved runtime files.
- [ ] Archive contains no caches, bytecode, private evidence, absolute local
      paths, secrets, or persisted thread identifiers.
- [ ] Clean temporary-home install, agent check, and uninstall pass.
- [ ] Public website, support, privacy, terms, repository, and release URLs load.
- [ ] Portal contains exactly five positive and three negative test cases.
- [ ] Skills-only bundle is submitted from an identity-verified developer account
      with Apps Management write access.
