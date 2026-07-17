# Aggregation Engine

Aggregation is configured with one or more canonical group fields and measures.
Functions are sum, count, unique count, average, minimum, maximum, median, first,
and last. Numeric functions type-check before execution; nulls can be ignored,
zero-filled, or treated as errors.

Deterministic post-aggregation stages support configured sorting, Top N, percentage
of total, dense rank, and running total. Preview returns input rows, group/output
counts, null impact, and errors without running the unbounded full job.
