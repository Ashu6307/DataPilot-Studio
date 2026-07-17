# Referential Integrity

The integrity engine accepts arbitrary parent and child frames, equal-arity
parent/reference field lists, optional per-key normalisation, null-reference and
duplicate-parent policies, severity, and failure action. Composite tuples are
indexed without business vocabulary.

Outputs distinguish valid child references, missing parents, duplicate parent
groups, null child references, and parents without children. Findings retain
minimal record references, keys, severity, reason codes, summary counts, and an
audit trail. A configured blocking failure is explicit in `IntegrityResult`.
