# Exact Join Engine

Joins accept independent left/right sources, equal-length key lists, trim/case/space
normalisation, null policy, duplicate-key policy, suffix, selected outputs, and
unmatched policy. Supported joins are inner, left, right, full, semi, and anti.

Before execution, normalised key frequencies classify one-to-one, one-to-many,
many-to-one, or many-to-many and estimate output rows. Many-to-many blocks unless
explicitly approved. Diagnostics report input counts, nulls, duplicates, estimated
and actual expansion. Evidence includes left/right unmatched tables and diagnostics;
fuzzy matching is deliberately absent.
