# Runtime Parameters

Supported parameter types are text, integer, decimal, boolean, date, datetime,
file/folder reference, choice, multi-choice, canonical field, and opaque
credential reference. Definitions include required/default/allowed values,
range/length/pattern validation, and allow/require/forbid override policy.

Nodes reference values as `${parameters.parameter_id}`. Resolution is recursive,
typed, payload-bounded, and audited. Secret parameters must be
`credential_reference`, accept only `credential://` values, and are redacted in
run audit. File/folder references reject parent traversal. Secret values are not
embedded in workflow JSON, plans, logs, or output manifests.
