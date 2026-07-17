# ADR-005: Closed typed expression tree

Status: Accepted — 2026-07-17

## Decision

Use Pydantic-discriminated literal, field, and allowlisted function nodes with static type validation and closed-dispatch evaluation. Do not expose text-to-code evaluation or arbitrary callables.

## Consequences

Expressions are portable, diffable, testable, and safe to render visually. New functions require a versioned contract, evaluator implementation, and tests.
