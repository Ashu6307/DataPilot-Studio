# ADR-003: Workflow configuration format

Status: Accepted — 2026-07-17

## Decision

Use canonical JSON validated by Pydantic. The root contains `schema_version`, `compatibility_version`, workflow/project identity and version, source connector settings, discovery overrides, canonical mappings, ordered operation nodes, validation rules, export configuration, and UTC timestamps.

Secrets are forbidden recursively by key names and common token patterns. Source paths and sample/source rows are not portable workflow data. Version updates create new immutable workflow records; JSON is sorted/indented when persisted for readable diffs.

## Compatibility

Schema version `1.0` is accepted by compatibility line `1`. Unknown major versions are blocked with an actionable error. Migrations must be pure, tested functions before a second schema version ships.

