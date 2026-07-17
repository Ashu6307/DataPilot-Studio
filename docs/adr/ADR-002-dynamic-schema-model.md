# ADR-002: Dynamic schema and canonical field model

Status: Accepted — 2026-07-17

## Decision

Represent source structure as discovery metadata and downstream structure as stable canonical field IDs. A mapping version resolves a source label or configured alias to one canonical field, constant/default, or restricted calculated field. Operations and validators may reference canonical IDs only.

Discovery returns observations, candidates, confidence, evidence, and warnings; it never silently becomes an immutable truth. Selected sheet/header and type overrides are workflow data. Name normalisation is used for suggestions, not destructive renaming.

## Consequences

Reorder is irrelevant; rename is repaired by mapping/alias review. Mapping ambiguity blocks execution. Multi-row header and table-region heuristics can improve without changing processor code. Lineage can point from output field to canonical ID and mapping version.

