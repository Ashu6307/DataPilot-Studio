# Governed Fuzzy Matching

Fuzzy stages require at least one candidate constraint. Blocking supports exact
field/category, month, first character, amount bucket, date window, and prefix
bucket. Candidate pairs are counted before scoring, estimated at 160 bytes per
pair for warning purposes, and stopped when the workflow budget is exceeded.

Available similarities are Levenshtein, token-sort, token-set, and normalised
string. Text is length bounded. Each candidate exposes method, score, threshold
through stage configuration, blocking evidence, contributing/conflicting fields,
and tie state. Cancellation is checked during block generation and scoring.

This design intentionally makes unrestricted all-to-all fuzzy comparison
invalid. A score tie or low-confidence pass creates a manual-review item.
