# Schema Drift and Mapping Repair

The drift service compares an observed `TableDiscovery` with an immutable workflow expectation. It emits independent findings for reorder, rename, addition, optional/required removal, type/nullability change, duplicate introduction, unexpected values, header-level change, sheet rename, table movement, and ambiguous mapping.

Suggestion precedence is deterministic: canonical ID, source alias, normalised label, approved synonym, then type-compatible label/sample evidence. Suggestions never mutate a mapping. Each includes confidence, evidence, competing candidates, type/sample comparison, and a proposed action.

Policy modes are `auto_accept_safe`, `warn_continue`, `require_confirmation`, and `block`. Only uniquely safe findings above configured thresholds may auto-accept. Ambiguous and low-confidence findings always require an explicit accept/reject/manual decision. Accepted repairs create a new mapping version and run-audit decision record; prior mapping versions remain immutable.
