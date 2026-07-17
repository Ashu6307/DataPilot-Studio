# Node Capability Registry

The registry is a closed map keyed by `(type_id, version)`. Every capability
declares category, typed input/output ports, Pydantic configuration schema,
validation method, preview/cancellation/checkpoint support, adapter ID, retry
classification, audit fields, and provider-neutral entitlement capability ID.

Adapters are registered explicitly. There is no module-name input, dynamic code
loading, plugin discovery, SQL, shell, `eval`, or `exec`. Application-owned
source adapters preserve workspace and fingerprint policy; engine adapters call
the existing DataPilot engines. Missing versions, schemas, entitlements, or
adapters fail actionably before background work starts.
