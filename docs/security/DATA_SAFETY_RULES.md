# Data Safety Rules

1. Never overwrite, rename, move, truncate, or delete an original input.
2. Read sources without write intent and fingerprint with SHA-256 before and after a run.
3. Create a unique UTC timestamp plus UUID directory per execution.
4. Generate output paths below the run directory; reject collisions rather than overwrite.
5. Treat identifier-like data as text and preserve leading zeros unless a configured conversion says otherwise.
6. Flag ambiguous dates and mixed types; no silent locale selection.
7. Never discard invalid rows silently. Emit rule ID, row ID, field ID, severity, reason code, explanation, and original value.
8. A failed, cancelled, or partially published run cannot be marked successful.
9. Enforce `read = written + rejected + filtered`; fail finalisation on mismatch.
10. Do not store complete source rows in SQLite, logs, telemetry, workflow JSON, or support bundles.
11. Reject workflow configurations containing plaintext passwords, keys, tokens, or secrets; use future credential references.
12. Escape formula-like output values to prevent spreadsheet formula injection.
13. Commit anonymised fixtures only. Keep runtime data under ignored `.datapilot/`.
14. Verify output files exist, reopen cleanly, and match the manifest before success.

