# Discovery Engine

Discovery converts source cells into reviewable candidates; it never silently declares business truth.

1. Load supported files read-only and retain source coordinates.
2. Partition each sheet into non-empty connected rectangular regions using blank row/column boundaries and repeated-header splits.
3. score one-, two-, and three-row header candidates within each region.
4. Forward-fill header levels horizontally for merged/blank group labels, join non-empty levels with the configured separator, and deterministically suffix duplicates.
5. Classify rows after the selected header as data, repeated header, grand total, subtotal, generated footer, signature, or note.
6. Profile a bounded sample and return decision, confidence, evidence, warnings, alternatives, and override fields.

Coordinates are one-based and inclusive. A `table_id` is derived from sheet and bounds, not a customer label. Overrides may select sheet, table, header rows, separator, and classified-row actions.

Excel merged ranges are inspection metadata only; sources remain immutable. CSV uses the same rectangular-region model without merged-cell metadata.
