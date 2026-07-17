# Safe Expression Engine

Calculated fields use a discriminated, typed expression tree containing literals, canonical field references, and allowlisted function nodes. The compiler validates field existence, arity, operand/output types, nesting depth, and output compatibility before rows are evaluated.

There is no parser or escape hatch for Python, SQL, JavaScript, shell, filesystem, network, imports, attributes, or callable objects. Evaluation is a closed dispatch table.

Execution date is injected into context, making `today` deterministic. Division by zero and other row errors follow configured `error_policy`; null propagation/coalescing follows `null_policy`. Results include affected/failed counts, before/after preview, reason codes, expression/calculation version, and field lineage.
