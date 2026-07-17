# ADR-004: Region-based discovery and multi-level headers

Status: Accepted — 2026-07-17

## Decision

Represent every discovered table with inclusive sheet coordinates, candidate header row sets, classifications, confidence, evidence, alternatives, and override fields. Flatten up to three reviewed header levels through forward-fill plus a configurable separator and deterministic duplicate suffixes.

## Consequences

Users can select among multiple regions without core business assumptions. Heuristics may improve while contracts remain stable. Discovery remains advisory and never deletes classified rows.
