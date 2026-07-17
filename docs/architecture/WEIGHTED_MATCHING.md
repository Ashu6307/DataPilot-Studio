# Weighted Multi-field Matching

Weighted stages declare exact, fuzzy, numeric-proximity, or date-proximity fields.
Positive Decimal weights must total exactly `1`. Required fields, missing-value
behavior, method-specific configuration, and threshold compatibility are
validated before execution.

Outputs retain each field score, configured weight, contribution, both values,
and reason code alongside the overall Decimal score. Ties and other ambiguity use
the same governed review path as fuzzy candidates; the scoring formula is never
hidden.
