# Security Architecture

## Assets and threats

Primary assets are source files, derived output, workflow intellectual property, credentials, audit evidence, and future license material. Initial threats include path traversal, accidental overwrite, malicious/corrupt office files, formula injection, secret leakage, resource exhaustion, configuration tampering, and misleading run status.

## Controls in this milestone

- Generated source/artifact IDs; basename sanitisation; allowlisted `.csv`, `.xlsx`, `.xlsm` input types; no client-controlled output path.
- Source fingerprint before/after execution, isolated run folders, unique output names, workbook re-open verification, and explicit failure/partial states.
- Excel cells beginning with formula sigils are written as strings unless an explicitly trusted formula feature is added later.
- Pydantic validates size-bounded/versioned workflow contracts; recursive secret-key scanning rejects plain secret material.
- CORS allowlist and loopback default. No authentication claim is made for this local milestone.
- SQLite contains metadata only. Structured logs contain IDs/counts/reason codes, never row values or secrets.
- Bounded discovery and preview limits; early file size reporting. Streaming/cancellation enforcement is deferred.
- Plugin and entitlement interfaces exist without loading untrusted code or binding to a license vendor.

## Residual risks

The development server is not a hardened multi-user service. Antivirus/sandbox scanning, ZIP/XML bomb controls, encrypted credential vault, signed plugins/installers, RBAC, tamper-evident audit signatures, CSP packaging, and remote tenancy are later security gates. The app must remain loopback-only until those controls exist.

