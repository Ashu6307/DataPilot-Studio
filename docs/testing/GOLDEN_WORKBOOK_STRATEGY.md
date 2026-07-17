# Golden Workbook Strategy

XLSX files are ZIP packages with non-deterministic timestamps and metadata, so correctness is not byte-for-byte equality.

Structural comparison opens workbooks without formula execution and checks sheet names/order, headers/order, cell value types, configured number formats, frozen panes, filters, reason/audit columns, formula-injection escaping, row reconciliation, and selected style semantics. Volatile creator/modified timestamps and ZIP metadata are ignored.

Golden fixtures contain anonymised synthetic data. A deliberate review step regenerates expected workbooks; normal tests never rewrite tracked golden files.
