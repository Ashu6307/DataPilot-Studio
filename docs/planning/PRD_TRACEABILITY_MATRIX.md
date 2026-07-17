# PRD Traceability Matrix

Status values: **Implemented** (code plus passing test), **Partial**, **Planned M1B**, **Deferred**, **Documentation only**.

| PRD section | Requirement ID | Requirement summary | Module | Milestone | Status | Related test | Notes/dependencies |
|---|---|---|---|---|---|---|---|
| 1-6 | PRD-FOUND-01 | Dynamic, safe, deterministic, local-first, reusable commercial platform | Whole product | M0+ | Implemented | `test_vertical_slice.py` | Foundation proven; commercial expansion deferred |
| 7 | PRD-XCUT-01 | No fixed rows/columns; metadata execution; immutable inputs; compatibility | Contracts/runtime | M0/M1 | Partial | `test_vertical_slice.py`, `test_discovery.py` | Core invariants implemented; cancellation/checkpoints M1B |
| 8 | FR-8-01 | Create blank/template project | Project service | M1 | Implemented | `test_api.py` | Blank project in slice; templates deferred |
| 8 | FR-8-02 | Clone/rename/archive/import/export projects | Project service | M1B | Planned M1B | future project lifecycle tests | Create/list only in slice |
| 8 | FR-8-03 | Separate vocabulary/schema/formats/branding from workflow | Contracts | M0 | Implemented | `test_workflow_schema.py` | Branding deferred |
| 8 | FR-8-04 | Version settings/workflows with change notes | Workflow repo | M1 | Implemented | `test_api.py` | Immutable version rows |
| 8 | FR-8-05 | Validate project portability | Workflow schema | M1B | Planned M1B | future portability test | Secret/path scan begins M0 |
| 8 | FR-8-06 | Separate config/cache/logs/data | Workspace | M0 | Implemented | `test_vertical_slice.py` | Isolated workspace/run layout |
| 8 | FR-8-07 | Credential references, no plaintext secrets | Contracts/security | M0 | Implemented | `test_workflow_schema.py` | Rejection scanner; vault deferred |
| 9 | FR-9-01 | Excel ingestion with sheet/table selection | Connector | M1 | Implemented | `test_discovery.py`, `test_api.py` | XLSX/XLSM read only |
| 9 | FR-9-02 | CSV/TSV/TXT/JSON/Parquet ingestion | Connector | M1/M2 | Partial | `test_discovery.py` | CSV now; others deferred |
| 9 | FR-9-03 | Folder/ZIP batch ingestion | Connector | M2 | Deferred | future batch tests | Not in slice |
| 9 | FR-9-04 | Parameterised database connector | Connector | M3 | Deferred | future connector contract tests | DuckDB internal adapter only |
| 9 | FR-9-05 | REST/pagination/auth-ref connector | Connector | M3 | Deferred | future API connector tests | No remote data |
| 9 | FR-9-06 | PDF/OCR connector | Connector | M4+ | Deferred | future PDF corpus | Unsupported initially |
| 9 | FR-9-07 | Preview/discovery/estimates/samples | Connector/discovery | M1 | Implemented | `test_discovery.py` | Bounded samples |
| 9 | FR-9-08 | Incremental ingestion | Connector | M2 | Deferred | future cursor tests | Fingerprints foundation only |
| 10 | FR-10-01 | Sheets, visibility, candidate regions | Discovery | M1 | Implemented | `test_discovery.py` | One primary region per sheet |
| 10 | FR-10-02 | Single/multi-row header confidence | Discovery | M1/M1B | Partial | `test_discovery.py` | Single row now; multi-row heuristic hardening M1B |
| 10 | FR-10-03 | Repeated headers and footer/totals | Discovery/cleaning | M1 | Implemented | `test_operations.py` | Footer is warning heuristic |
| 10 | FR-10-04 | Types/nulls/unique/min-max/patterns | Profiler | M1 | Implemented | `test_discovery.py` | Sampled for large sources |
| 10 | FR-10-05 | Suggest semantic roles | Profiler | M1 | Implemented | `test_discovery.py` | Evidence-based heuristic |
| 10 | FR-10-06 | Suggest primary/composite keys | Profiler | M1/M1B | Partial | `test_discovery.py` | Single key now; composite M1B |
| 10 | FR-10-07 | Detect multiple separated tables | Discovery | M1B | Planned M1B | future region tests | Report warning now |
| 10 | FR-10-08 | Classify schema drift | Schema | M1B | Planned M1B | future drift tests | Mapping reuse proof in slice |
| 11 | FR-11-01 | Searchable source-to-canonical mapping | Mapping UI/engine | M1 | Implemented | `test_mapping.py`, Playwright | Editable mapping grid; search hardening M1B |
| 11 | FR-11-02 | Calculated/constant canonical fields | Mapping | M1/M1B | Partial | `test_mapping.py` | Constant/default now; calculations M1B |
| 11 | FR-11-03 | One/many/conditional mappings | Mapping | M2 | Deferred | future mapping tests | One-to-one now |
| 11 | FR-11-04 | Synonyms and approved mappings | Mapping | M1 | Implemented | `test_mapping.py` | Workflow scoped |
| 11 | FR-11-05 | Duplicate/type compatibility validation | Mapping | M1 | Implemented | `test_mapping.py` | Blocks ambiguity |
| 11 | FR-11-06 | Preview mapped values | Mapping/UI | M1 | Implemented | `test_api.py`, Playwright | Bounded |
| 11 | FR-11-07 | Different source mappings, same workflow | Mapping | M1 | Implemented | `test_vertical_slice.py` | Reordered fixture proof |
| 12 | FR-12-01 | Trim/case/non-printable | Operations | M1 | Implemented | `test_operations.py` | Versioned registry |
| 12 | FR-12-02 | Explicit/pattern/dictionary replacement | Operations | M1B | Planned M1B | future replace tests | Null dictionary only now |
| 12 | FR-12-03 | Extract typed values/ranges | Operations | M2 | Deferred | future extraction tests | Not in slice |
| 12 | FR-12-04 | Split/merge columns | Operations | M2 | Deferred | future structure tests | Not in slice |
| 12 | FR-12-05 | Standardise dates/contact/units/nulls | Operations | M1/M2 | Partial | `test_operations.py` | Nulls now; other domains deferred |
| 12 | FR-12-06 | Controlled fill/derive missing | Operations | M2 | Deferred | future fill tests | Defaults in mapping only |
| 12 | FR-12-07 | Remove rows/blanks/columns/repeated headers | Operations | M1 | Implemented | `test_operations.py` | Select fields covers columns |
| 12 | FR-12-08 | Optional original-value lineage | Lineage | M1B | Planned M1B | future lineage tests | Audit metrics now |
| 13 | FR-13-01 | Filter/sort/select/rename/reorder | Operations | M1/M2 | Partial | `test_operations.py` | Select/rename/reorder now |
| 13 | FR-13-02 | Append mapped tables | Operations | M2 | Deferred | future append tests | Not in slice |
| 13 | FR-13-03 | Join tables safely | Operations | M2 | Deferred | future join tests | Not in slice |
| 13 | FR-13-04 | Group/aggregate/rank/running metrics | Operations | M1B/M2 | Planned M1B | future calculation tests | Not in slice |
| 13 | FR-13-05 | Pivot/unpivot | Operations | M2 | Deferred | future reshape tests | Not in slice |
| 13 | FR-13-06 | Window/date/ageing/conditional fields | Operations | M2 | Deferred | future calculation tests | Not in slice |
| 13 | FR-13-07 | Explode/aggregate multi-value cells | Operations | M2 | Deferred | future structure tests | Not in slice |
| 13 | FR-13-08 | Heterogeneous union with lineage | Operations | M2 | Deferred | future union tests | Not in slice |
| 14 | FR-14-01..07 | Condition builder, typed calculations, reusable/versioned rules, evaluator/tests | Rule engine | M1/M2 | Partial | `test_validators.py` | Simple validation configs now; visual conditions/calculations deferred |
| 15 | FR-15-01 | Required/unique/range/pattern/allowed checks | Validation | M1 | Implemented | `test_validators.py` | All included |
| 15 | FR-15-02 | Cross-field conditional validation | Validation | M2 | Deferred | future rule tests | Not in slice |
| 15 | FR-15-03 | Referential integrity | Validation | M2 | Deferred | future reference tests | Not in slice |
| 15 | FR-15-04 | Duplicate/near-duplicate detection | Validation | M1/M2 | Partial | `test_validators.py` | Exact unique now; near duplicate deferred |
| 15 | FR-15-05 | Schema/type validation | Validation | M1 | Implemented | `test_validators.py` | Ambiguity stays visible |
| 15 | FR-15-06 | Transparent outlier/anomaly flags | Quality | M2 | Deferred | future anomaly tests | Not in slice |
| 15 | FR-15-07 | Dimension quality score | Quality | M2 | Deferred | future score tests | Counts only now |
| 15 | FR-15-08 | Info/warning/error severities | Validation | M1 | Implemented | `test_validators.py` | Adds blocking per brief |
| 16 | FR-16-01..08 | Staged exact/tolerance/fuzzy reconciliation and review outputs | Reconciliation | M2 | Deferred | future reconciliation suite | Explicitly outside slice |
| 17 | FR-17-01..07 | Key-based workbook/data comparison and review outputs | Comparison | M2 | Deferred | future comparison suite | Explicitly outside slice |
| 18 | FR-18-01..08 | Typed visual workflows, modes, progress/cancel/checkpoints/versioning | Workflow platform | M3 | Deferred | future DAG/E2E tests | Linear ordered slice only |
| 19 | FR-19-01..07 | Triggers/schedules/stability/retry/dependencies/queues/recovery | Orchestration | M3 | Deferred | future scheduler tests | Manual runs only |
| 20 | FR-20-01..07 | Workbook productivity, formulas, health and formatting | Excel tools | M2+ | Deferred | future workbook corpus | Export formatting only |
| 21 | FR-21-01 | Excel detail/summary/error/audit export | Export | M1 | Implemented | `test_vertical_slice.py` | Required pack |
| 21 | FR-21-02 | Dynamic order/formats/widths/filters/freeze/conditional | Export | M1 | Implemented | `test_vertical_slice.py` | Safe limits and error highlighting |
| 21 | FR-21-03 | Branded template packs | Report | M2 | Deferred | future golden tests | Base theme only |
| 21 | FR-21-04 | Pivot summaries and KPI cards | Report | M2 | Deferred | future report tests | Counts summary only |
| 21 | FR-21-05 | Interactive dashboards | Reports/UI | M4+ | Deferred | future dashboard E2E | Not in slice |
| 21 | FR-21-06 | CSV/Parquet/JSON/API outputs | Export | M2 | Deferred | future exporter tests | Excel only in slice |
| 21 | FR-21-07 | Publication checks | Runtime/export | M1 | Implemented | `test_vertical_slice.py` | Reopen and reconcile |
| 22 | FR-22-01..07 | Governed AI mapping/workflow/explanations/summaries | AI | M6 | Deferred | future AI guardrail tests | Remote AI prohibited now |
| 23 | FR-23-01..07 | Safe file naming/routing/hash/package/retention/watcher | File automation | M3 | Deferred | future filesystem tests | Hash/name safety foundation only |
| 24 | FR-24-01..07 | Signed licensing, seats, grace, features, transfer/admin/trial | Licensing | M4 | Deferred | capability/entitlement contract tests | Provider-neutral interface only |
| 25 | FR-25-01 | Plugin manifest | Plugin SDK | M0 | Implemented | `test_plugin_contracts.py` | Schema only |
| 25 | FR-25-02 | Connector/processor/validator/exporter/UI contracts | Plugin SDK | M0 | Implemented | `test_plugin_contracts.py` | No UI extension runtime |
| 25 | FR-25-03 | Install/enable/compatibility | Plugin SDK | M6 | Deferred | future plugin lifecycle tests | Registry built-ins only |
| 25 | FR-25-04 | Plugin isolation | Plugin runtime | M6 | Deferred | future sandbox tests | No untrusted loading |
| 25 | FR-25-05 | Signed packages | Plugin runtime | M6 | Deferred | future signature tests | Not in slice |
| 25 | FR-25-06 | Test harness/fixtures | Plugin SDK | M0 | Implemented | `test_plugin_contracts.py` | Contract fixture |
| 25 | FR-25-07 | Failure boundaries/diagnostics | Plugin runtime | M6 | Deferred | future isolation tests | Interface errors only |
| 26 | PRD-UX-01 | Guided, dense, accessible and recoverable workspace/screens | Web | M1/M1B | Partial | Vitest + Playwright | Guided slice responsive; autosave/dark/advanced grids M1B |
| 27-30 | PRD-ARCH-01 | Modular monolith, typed API, storage, security, reliability/observability | Platform | M0+ | Partial | API/safety tests | Local foundation implemented; cloud/RBAC/signing/checkpoints deferred |
| 31 | PRD-QA-01 | Multi-layer tests and release gates | Quality | M0+ | Implemented | all test suites | Initial gates pass; upgrade/security/perf expand by phase |
| 32 | PRD-COM-01 | Trustworthy licensing/packaging | Commercial | M4 | Documentation only | future commercial gates | No enforcement in slice |
| 33-36 | PRD-ROADMAP-01 | Phased delivery, DoD, support, risks | Planning | M0 | Documentation only | traceability review | Roadmap adopted |
| 37 | US-001..010 | P0 project/import/discovery/mapping/clean/validate/export/runs/compat/cancel | Vertical slice | M1/M1B | Partial | API/vertical/E2E suites | Core journey implemented; cancel and migrations M1B |
| 37 | US-011..024 | P1 profiles/drift/advanced ops/reports/visual workflow/support | Core/advanced | M1/M2/M3 | Partial | per-module future suites | Save profile now; remainder staged |
| 37 | US-025..035 | P2 scheduler/connectors/dashboard/team/license/update/AI | Later platform | M3-M6 | Deferred | future phase tests | Explicit deferral |
| 37 | US-036..040 | P3 plugins/marketplace/cloud/SSO/audit ledger | Ecosystem | M6 | Deferred | future enterprise tests | Explicit deferral |
| 38 | PRD-SYSAC-01 | System-wide dynamic/safety/audit/error/accessibility criteria | Whole product | M1+ | Partial | `test_vertical_slice.py`, Playwright | Initial slice passes; deferred modules retain their criteria |
| 39-42 | PRD-KICKOFF-01 | Reference workflows, sequence, fixtures, API, review gates | Delivery | M0/M1 | Partial | all initial suites | Initial profile and fixtures pass; five-profile hardening M1B |

## Review rule

Update this matrix in the same change that moves a requirement to Implemented. A status change requires a named automated test and evidence that the relevant quality gates passed.
