# DAG Runtime

Full runs enter through `LocalDagExecutor.submit`; synchronous full-execution
routes are not provided. A published workflow is validated and planned, then
executed in a background thread. Independent ready start nodes use the reviewed
concurrency budget. Other nodes follow dependency order with cooperative
cancellation between adapters and inside long-running reconciliation stages.

Every node attempt has a lifecycle record. Outputs are materialized below a
run-specific `partial` directory, fingerprinted, and recorded as metadata. Only
successful completion moves the isolated directory to `completed` and sets
`output_available`. Failed, cancelled, waiting, or recovery-required runs cannot
appear successful.

On process startup, non-terminal runs become `recovery_required`. Resume reloads
fingerprinted artifacts and completed-node state. Retries create a linked new run
and are blocked when the plan contains non-deterministic nodes.
