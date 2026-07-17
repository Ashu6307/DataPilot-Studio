# Subflows

Subflows are project-scoped, versioned definitions with public typed ports,
runtime parameters, internal nodes/edges, and pinned dependencies. A reference
node declares its exact subflow ID/version plus explicit input/output bindings.

Expansion namespaces internal node and edge IDs with the reference node ID,
preserving lineage and avoiding collisions. Missing versions, recursion, and
depth-budget breaches block execution. Published parent versions remain pinned;
upgrading a subflow requires a new parent workflow version and produces a
reviewable diff.
