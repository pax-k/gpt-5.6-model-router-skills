# Policy attestations

For the v0.4.0 hook-bearing candidate:

- Listing, starter prompts, and hook disclosure describe the implemented governed-routing behavior.
- The plugin has no authentication, MCP server, connector, hosted service, analytics, advertising, tracking, or credential collection.
- Local setup writes are limited to ten managed templates, backups, one managed depth entry, and ownership state. Trusted hooks additionally keep bounded hash-and-route metadata beneath `PLUGIN_DATA`. They do not persist raw prompts, messages, diffs, tool output, or secrets.
- The plugin does not bypass runtime permissions. Model selection is advisory for ordinary work; critical execution, independent review, authority, and protocol invariants are hook-enforced after trust.
- Routed children are leaves unless given the exact one-level grant; every descendant is a leaf. Full-history inheritance is reserved for explicitly recorded inherited-root execution without custom role or model fields.
- External, destructive, credentialed, costly, and out-of-scope actions remain subject to active Codex authority.
- The candidate contains no secrets, private rollout identifiers, local absolute paths, cached bytecode, or private acceptance artifacts.

Final policy and legal attestations remain unchecked until the user explicitly confirms them immediately before **Submit for Review**.
