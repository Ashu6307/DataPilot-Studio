# Match Normalisation

Normalisation is a closed, deterministic pipeline of stable operation IDs. The
initial registry covers trim/collapse/case, punctuation, prefixes/suffixes,
approved dictionaries, Unicode, null-like values, controlled leading zeros,
selected separators, canonical dates, and canonical numerics.

Every operation has configuration version `1`; every pipeline has an ID and
version. Preview returns original and normalised values plus per-step input,
output, changed flag, and reason code. Leading zeros are preserved by default and
may be removed only with explicit operation approval. Normalised values never
overwrite source evidence.
