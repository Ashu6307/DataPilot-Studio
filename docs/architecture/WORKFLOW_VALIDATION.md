# Workflow Validation

Validation checks secret literals, payload/node/edge budgets, duplicate IDs,
capability versions, entitlements, configuration schemas, parameter references,
port existence/type/cardinality, required inputs/outputs, cycles, multiple-start
policy, and reachability. Findings carry severity, reason code, explanation,
resolution, and node/edge/parameter reference.

Parameter placeholders are validated against their declared default for static
configuration checks and are re-coerced at execution. Blocking or error findings
prevent planning and publication. The UI problems panel links findings back to
nodes; the API returns the same contract.
