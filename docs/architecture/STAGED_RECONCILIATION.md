# Staged Reconciliation

A `ReconciliationWorkflow` contains uniquely identified, ascending-priority
stages. Each stage declares distinct left/right keys, pipelines, method,
thresholds, tolerances, blocking constraints, tie policy, cardinality,
duplicate behavior, classification, and match-consumption policy.

Supported methods are exact, normalised exact, numeric tolerance, date
tolerance, combined exact/tolerance, fuzzy text, and weighted multi-field. The
default waterfall removes both sides of an accepted one-to-one match before the
next stage. Reuse is possible only through explicit configuration.

Each match exposes record lineage, stage, method, score, matched fields,
differences, reason, confidence, and review status. Ties, duplicates, ambiguous
candidates, and low-confidence fuzzy candidates are not silently accepted.
