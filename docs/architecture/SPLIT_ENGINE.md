# Split Engine

Splits support one/many canonical fields, year/month/quarter extraction, a closed
typed boolean condition, minimum group size, and maximum rows per file. Modes are
separate Excel workbooks, one multi-sheet workbook, separate CSVs, and ZIP.

Template variables are sanitised, traversal tokens and invalid characters are
removed, duplicate names receive deterministic suffixes, sheet names are capped at
31 characters, and resolved paths must remain below the run output directory.
Existing paths cause failure rather than overwrite. Every artifact records row
count, media type, size, and SHA-256; ZIP entry timestamps and selection are stable.
