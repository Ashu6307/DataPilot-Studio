# Decision Memory

Decision memory is an optional, explicit metadata layer for approved synonyms,
canonical mappings, aliases, rejected aliases, and review patterns. It is project
scoped by default; workflow scope requires a workflow ID. Entries include expiry,
confidence, creator, timestamps, and active state.

Entries are reviewable and exportable. User deletion erases stored source,
canonical, expiry, confidence, and creator values while retaining an inactive
identifier, scope, kind, and deactivation audit event. Current matching does not silently apply memory; future
ranking may consult active entries only after preserving stage blocking,
threshold, ambiguity, and review rules. No learning or autonomous behavior is
present.
