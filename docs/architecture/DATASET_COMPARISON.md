# Dataset Comparison

`ComparisonConfiguration` identifies two canonical datasets, one or more
business-key fields, null and duplicate policies, fields to compare/ignore,
normalisation, type behavior, tolerances, and null equivalence. Row position is
lineage only and is never a key unless exposed as a selected canonical field.

The engine builds bounded key indexes, reports invalid and duplicate keys before
pairing, and emits added, removed, modified, unchanged, duplicate, invalid, and
ambiguous records. Modified records contain typed field differences with both
values, numeric impact, materiality, and a stable reason code.

Structure comparison adapts the Milestone 1B schema-drift analyzer. Added,
removed, remapped, reordered, type, nullability, value-set, uniqueness, header,
and table-selection changes are translated into a `StructureComparisonResult`;
there is no second drift implementation.
