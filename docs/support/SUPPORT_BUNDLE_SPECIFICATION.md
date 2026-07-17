# Support Bundle Specification

Support export is a two-step, user-controlled flow: build a preview manifest, then export only after approval.

Included by default: product/OS/dependency versions, sanitised non-secret configuration, run IDs/status/counts/durations, error and reason codes, correlation IDs, bounded sanitised logs, test diagnostics, and a manifest with hashes.

Excluded by default: source files/rows/samples, output data, passwords, tokens, cookies, API/license/credential values, environment-variable values, absolute user paths, and unmasked sensitive values. Screenshots require a separate opt-in and are listed in preview.

Sanitisation is recursive by key and value pattern. Export re-runs sanitisation, writes a unique ZIP in an isolated support directory, and never mutates runtime evidence.
