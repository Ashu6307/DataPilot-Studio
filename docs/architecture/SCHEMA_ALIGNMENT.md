# Schema Alignment

A `SchemaAlignmentPlan` versions canonical fields, per-source mapping sets, user
decisions, and missing/extra policies. The matrix contains a cell per source/field
with confidence, observed/target type, conversion, status, and warnings; extra fields
are explicit cells.

Required gaps reject, quarantine, block, or use an approved supplied value according
to policy. Optional gaps become typed nulls. Mapping output is safely cast to canonical
types and receives `__source_id`, `__source_file`, `__source_table`, and
`__source_row` lineage. Each saved plan writes per-source decision JSON to the
append-only alignment decision audit table.
