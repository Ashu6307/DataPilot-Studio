# Append and Union Engine

Aligned Polars tables are concatenated with diagonal relaxed schema handling, then
ordered by configured canonical fields. Lineage fields are retained. Duplicate
selection excludes internal lineage columns unless explicit keys are configured.

Policies are keep all, remove exact, keep first, keep last, reject, or route to
review. Rejected/review rows carry stable reason codes. Runtime manifests report
files considered/accepted/rejected, rows read/output/rejected, duplicate rows,
warnings, plan version, and output fingerprints.
