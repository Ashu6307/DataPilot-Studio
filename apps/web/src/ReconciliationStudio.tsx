import {
  AlertTriangle, ArrowDown, ArrowUp, CheckCircle2, Database, Download, Eye, FileOutput,
  FileSearch, Fingerprint, GitCompareArrows, GripVertical, Layers3, LoaderCircle, Play,
  Plus, Scale, Search, Settings2, ShieldCheck, SlidersHorizontal, Trash2, UploadCloud, X,
} from "lucide-react";
import { useMemo, useState, type ChangeEvent } from "react";
import { api } from "./api";
import { DataTable } from "./components/DataTable";
import { MetricCard } from "./components/MetricCard";
import { StatusChip } from "./components/StatusChip";
import type {
  BackgroundJob, ColumnProfile, DiscoveryResult, MatchMethod, MatchStage, Project,
  ReconciliationManifest, ReconciliationResult, ReconciliationRunRecord, ReconciliationWorkflow,
  ReviewItem, RunRecord, SourceHandle,
} from "./types";

const screenLabels = [
  "Project setup", "Left and right datasets", "Key definition", "Structure comparison",
  "Comparison fields", "Normalisation builder", "Stage builder", "Numeric tolerance",
  "Date tolerance", "Fuzzy configuration", "Weighted score", "Candidate safety",
  "Execution preview", "Live progress", "Summary", "Field differences", "Manual review",
  "Candidate drawer", "Decision history", "Evidence export",
];

interface StageDraft { id: string; name: string; method: MatchMethod }

const methodLabels: Record<MatchMethod, string> = {
  exact: "Exact match",
  normalised_exact: "Normalised exact",
  numeric_tolerance: "Numeric tolerance",
  date_tolerance: "Date tolerance",
  combined_exact_tolerance: "Combined exact + tolerance",
  fuzzy_text: "Fuzzy text candidate",
  weighted_multi_field: "Weighted multi-field",
};

function fieldNames(discovery: DiscoveryResult | null): ColumnProfile[] {
  return discovery?.tables[0]?.columns ?? [];
}

export function ReconciliationStudio({ project }: { project: Project }) {
  const [leftSource, setLeftSource] = useState<SourceHandle | null>(null);
  const [rightSource, setRightSource] = useState<SourceHandle | null>(null);
  const [leftDiscovery, setLeftDiscovery] = useState<DiscoveryResult | null>(null);
  const [rightDiscovery, setRightDiscovery] = useState<DiscoveryResult | null>(null);
  const [keyField, setKeyField] = useState("");
  const [comparisonFields, setComparisonFields] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [normalisation, setNormalisation] = useState("trim_lower");
  const [numericField, setNumericField] = useState("");
  const [numericTolerance, setNumericTolerance] = useState("5");
  const [dateField, setDateField] = useState("");
  const [dateTolerance, setDateTolerance] = useState(2);
  const [fuzzyField, setFuzzyField] = useState("");
  const [blockField, setBlockField] = useState("");
  const [fuzzyThreshold, setFuzzyThreshold] = useState("0.85");
  const [stages, setStages] = useState<StageDraft[]>([
    { id: "exact_primary", name: "Exact business key", method: "exact" },
  ]);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [preview, setPreview] = useState<ReconciliationResult | null>(null);
  const [previewedWorkflow, setPreviewedWorkflow] = useState<ReconciliationWorkflow | null>(null);
  const [job, setJob] = useState<BackgroundJob | null>(null);
  const [run, setRun] = useState<RunRecord | null>(null);
  const [runRecord, setRunRecord] = useState<ReconciliationRunRecord | null>(null);
  const [manifest, setManifest] = useState<ReconciliationManifest | null>(null);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [selectedReview, setSelectedReview] = useState<ReviewItem | null>(null);
  const [decisionHistory, setDecisionHistory] = useState<Array<Record<string, unknown>>>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const leftFields = fieldNames(leftDiscovery);
  const rightFields = fieldNames(rightDiscovery);
  const commonFields = useMemo(() => {
    const right = new Set(rightFields.map((field) => field.source_name));
    return leftFields.filter((field) => right.has(field.source_name));
  }, [leftFields, rightFields]);
  const filteredFields = commonFields.filter((field) =>
    `${field.source_name} ${field.inferred_type}`.toLowerCase().includes(search.toLowerCase())
  );
  const structureDifferences = useMemo(() => {
    const left = new Map(leftFields.map((field, index) => [field.source_name, { field, index }]));
    const right = new Map(rightFields.map((field, index) => [field.source_name, { field, index }]));
    const findings: Array<Record<string, unknown>> = [];
    for (const [name, value] of left) {
      if (!right.has(name)) findings.push({ field: name, change: "removed in right", severity: "error" });
      else if (right.get(name)?.field.inferred_type !== value.field.inferred_type)
        findings.push({ field: name, change: "data type changed", severity: "warning" });
      else if (right.get(name)?.index !== value.index)
        findings.push({ field: name, change: "reordered", severity: "information" });
    }
    for (const name of right.keys()) if (!left.has(name)) findings.push({ field: name, change: "added in right", severity: "warning" });
    return findings;
  }, [leftFields, rightFields]);

  async function uploadSide(side: "left" | "right", event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; if (!file) return;
    setBusy(`Inspecting ${side} dataset…`); setError(null); setPreview(null);
    try {
      const source = await api.uploadSource(project.id, file);
      const discovery = await api.discover(source.id);
      if (!discovery.tables[0]) throw new Error(`No usable table found in ${side} dataset.`);
      if (side === "left") { setLeftSource(source); setLeftDiscovery(discovery); }
      else { setRightSource(source); setRightDiscovery(discovery); }
      const other = side === "left" ? rightDiscovery : leftDiscovery;
      const current = discovery.tables[0].columns;
      const otherNames = new Set(other?.tables[0]?.columns.map((field) => field.source_name) ?? []);
      const shared = current.find((field) => otherNames.has(field.source_name))?.source_name;
      if (shared) {
        setKeyField((value) => value || shared);
        setComparisonFields((value) => value.length ? value : [shared]);
        setFuzzyField((value) => value || shared);
        setBlockField((value) => value || shared);
      }
      const numeric = current.find((field) => ["integer", "decimal"].includes(field.inferred_type))?.source_name;
      const date = current.find((field) => ["date", "datetime"].includes(field.inferred_type))?.source_name;
      if (numeric) setNumericField((value) => value || numeric);
      if (date) setDateField((value) => value || date);
    } catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(null); event.target.value = ""; }
  }

  function addStage(method: MatchMethod) {
    const stamp = stages.length + 1;
    setStages([...stages, { id: `${method}_${stamp}`, name: methodLabels[method], method }]);
    setPreview(null);
  }

  function moveStage(index: number, delta: number) {
    const target = index + delta; if (target < 0 || target >= stages.length) return;
    const next = [...stages]; [next[index], next[target]] = [next[target], next[index]];
    setStages(next); setPreview(null);
  }

  function dropStage(target: number) {
    if (dragIndex === null || dragIndex === target) return setDragIndex(null);
    const next = [...stages]; const [item] = next.splice(dragIndex, 1); next.splice(target, 0, item);
    setStages(next); setDragIndex(null); setPreview(null);
  }

  function buildStage(draft: StageDraft, priority: number): MatchStage {
    const numeric = numericField || keyField;
    const date = dateField || keyField;
    const fuzzy = fuzzyField || keyField;
    const block = blockField || keyField;
    const base: MatchStage = {
      schema_version: "2b.1", id: draft.id, name: draft.name, priority,
      left_key_fields: [keyField], right_key_fields: [keyField], method: draft.method,
      threshold: draft.method === "fuzzy_text" ? fuzzyThreshold : "1",
      tie_breaking_rule: "none", one_to_one: true, duplicate_handling: "ambiguous",
      output_classification: "matched", continue_policy: "remove_matches",
    };
    if (draft.method === "normalised_exact") base.normalisation_pipelines = [normalisationPipeline(normalisation)];
    if (draft.method === "numeric_tolerance") {
      base.left_key_fields = [numeric]; base.right_key_fields = [numeric]; base.threshold = "0.5";
      base.numeric_tolerances = { [numeric]: { mode: "absolute_difference", tolerance: numericTolerance } };
      base.candidate_constraints = [{ id: `block_${draft.id}`, method: "exact", left_field: block, right_field: block }];
    }
    if (draft.method === "date_tolerance") {
      base.left_key_fields = [date]; base.right_key_fields = [date]; base.threshold = "1";
      base.date_tolerances = { [date]: { mode: "calendar_days", days: dateTolerance } };
      base.candidate_constraints = [{ id: `block_${draft.id}`, method: "exact", left_field: block, right_field: block }];
    }
    if (draft.method === "combined_exact_tolerance") {
      base.left_key_fields = [numeric, date]; base.right_key_fields = [numeric, date]; base.threshold = "0.5";
      base.numeric_tolerances = { [numeric]: { mode: "absolute_difference", tolerance: numericTolerance } };
      base.date_tolerances = { [date]: { mode: "calendar_days", days: dateTolerance } };
      base.candidate_constraints = [{ id: `block_${draft.id}`, method: "exact", left_field: block, right_field: block }];
    }
    if (draft.method === "fuzzy_text") {
      base.left_key_fields = [fuzzy]; base.right_key_fields = [fuzzy];
      base.candidate_constraints = [{ id: `block_${draft.id}`, method: "exact", left_field: block, right_field: block }];
      base.fuzzy_fields = [{ left_field: fuzzy, right_field: fuzzy, method: "token_sort_similarity", threshold: fuzzyThreshold }];
    }
    if (draft.method === "weighted_multi_field") {
      base.left_key_fields = [fuzzy]; base.right_key_fields = [fuzzy]; base.threshold = "0.7";
      base.candidate_constraints = [{ id: `block_${draft.id}`, method: "exact", left_field: block, right_field: block }];
      base.weighted_fields = [
        { id: "text_score", left_field: fuzzy, right_field: fuzzy, comparison: "fuzzy", fuzzy_method: "token_sort_similarity", weight: "0.6" },
        { id: "block_score", left_field: block, right_field: block, comparison: "exact", weight: "0.4" },
      ];
    }
    return base;
  }

  function buildWorkflow(): ReconciliationWorkflow {
    if (!leftSource || !rightSource || !keyField) throw new Error("Select both datasets and a common business key.");
    if (!stages.length) throw new Error("At least one matching stage is required.");
    return {
      schema_version: "2b.1", id: previewedWorkflow?.id ?? crypto.randomUUID(), version: 1,
      project_id: project.id, display_name: `${project.name} reconciliation`,
      left_dataset_id: leftSource.id, right_dataset_id: rightSource.id,
      comparison: {
        schema_version: "2b.1", id: crypto.randomUUID(), version: 1, project_id: project.id,
        left_dataset_id: leftSource.id, right_dataset_id: rightSource.id,
        business_key_fields: [keyField], key_null_policy: "invalid", duplicate_key_policy: "report",
        compare_fields: comparisonFields, ignore_fields: [], comparison_rules: [], key_normalisation: {},
      },
      stages: stages.map((stage, index) => buildStage(stage, index + 1)),
      comparison_fields: comparisonFields.map((field_id) => ({ field_id })),
      evidence_fields: [...new Set([keyField, fuzzyField, blockField, numericField, dateField].filter(Boolean))],
      budgets: {
        maximum_candidate_pairs: 1000000, maximum_duplicate_group_size: 10000,
        maximum_review_items: 50000, maximum_fuzzy_fields: 5, minimum_fuzzy_threshold: "0.70",
        maximum_export_sheets: 30, maximum_export_rows_per_sheet: 1000000,
        maximum_execution_time_warning_seconds: 1800, maximum_snapshot_fields: 20,
      },
      export: { formats: ["excel", "csv", "json", "zip"], include_outputs: [], filename_prefix: "reconciliation_evidence" },
    };
  }

  async function previewWorkflow() {
    setBusy("Estimating candidates and running bounded preview…"); setError(null);
    try {
      const workflow = buildWorkflow();
      await api.saveReconciliationWorkflow(workflow);
      setPreview(await api.previewReconciliation(workflow)); setPreviewedWorkflow(workflow);
    } catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(null); }
  }

  async function executeWorkflow() {
    if (!previewedWorkflow) return;
    setBusy("Submitting reconciliation background job…"); setError(null);
    try {
      const submitted = await api.submitReconciliation(previewedWorkflow); setJob(submitted); setBusy(null);
      for (;;) {
        const current = await api.getReconciliationJob(submitted.id); setJob(current);
        if (["succeeded", "partial"].includes(current.status) && current.run_id) {
          const [genericRun, record, outputManifest, reviewItems] = await Promise.all([
            api.getRun(current.run_id), api.getReconciliationRun(current.run_id),
            api.getReconciliationManifest(current.run_id), api.getReconciliationReviews(current.run_id),
          ]);
          setRun(genericRun); setRunRecord(record); setManifest(outputManifest); setReviews(reviewItems); return;
        }
        if (["failed", "cancelled"].includes(current.status)) {
          if (current.error_message) setError(current.error_message); return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 350));
      }
    } catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(null); }
  }

  async function openReview(item: ReviewItem) {
    setSelectedReview(item);
    try { setDecisionHistory(await api.getReviewDecisions(item.id)); }
    catch { setDecisionHistory([]); }
  }

  async function decide(item: ReviewItem, decision: string) {
    setBusy("Recording immutable review decision…"); setError(null);
    try {
      const selected = decision === "approve_alternate_candidate"
        ? String((item.candidates[0]?.right as Record<string, unknown> | undefined)?.record_id ?? "") : undefined;
      await api.decideReview(item.id, decision, selected);
      if (runRecord) setReviews(await api.getReconciliationReviews(runRecord.run_id));
      await openReview({ ...item, status: decision.startsWith("approve") ? "approved" : "rejected" });
    } catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(null); }
  }

  const summary = runRecord?.summary ?? preview?.summary;
  const zipIndex = run?.artifacts.findIndex((path) => path.endsWith(".zip")) ?? -1;
  const normalisationSample = String(leftDiscovery?.tables[0]?.preview[0]?.[keyField] ?? "  Example-Key  ");
  return <>
    <div className="screen-head"><div><span className="eyebrow teal">MILESTONE 2B</span><h1>Reconcile changing datasets with visible evidence.</h1><p>Compare by business key, build a governed match waterfall, and route ambiguity to review.</p></div><span className="step-pill">Reconciliation studio</span></div>
    {busy && <div className="busy-banner" role="status"><LoaderCircle className="spin" size={18}/>{busy}</div>}
    {error && <div className="error-banner" role="alert"><AlertTriangle/><div><strong>Reconciliation needs attention</strong><span>{error}</span></div><button onClick={() => setError(null)} aria-label="Dismiss"><X/></button></div>}
    <section className="composition-step-grid reconciliation-step-grid" aria-label="Reconciliation workflow screens">
      {screenLabels.map((label, index) => <article key={label} className={(index < 6 && leftDiscovery && rightDiscovery) || (index >= 12 && preview) ? "composition-step complete" : "composition-step"}><span>{index + 1}</span><strong>{label}</strong></article>)}
    </section>
    <section className="metrics-grid">
      <MetricCard icon={Database} label="Left rows" value={leftDiscovery?.tables[0]?.row_count_estimate ?? 0} note={leftSource?.original_filename ?? "Select dataset"}/>
      <MetricCard icon={Database} label="Right rows" value={rightDiscovery?.tables[0]?.row_count_estimate ?? 0} note={rightSource?.original_filename ?? "Select dataset"}/>
      <MetricCard icon={Scale} label="Match stages" value={stages.length} note="Ordered and one-to-one"/>
      <MetricCard icon={AlertTriangle} label="Review pending" value={summary?.review_pending ?? 0} note="Never silently approved" tone={summary?.review_pending ? "warning" : "success"}/>
    </section>
    <div className="workspace-grid">
      {(["left", "right"] as const).map((side) => { const source = side === "left" ? leftSource : rightSource; const discovery = side === "left" ? leftDiscovery : rightDiscovery; return <section className="panel" key={side}><div className="panel-title"><div><span className="eyebrow">{side.toUpperCase()} DATASET</span><h3>{source?.original_filename ?? `Select ${side} source`}</h3></div><UploadCloud/></div><label className="drop-zone compact-drop"><input type="file" accept=".csv,.xlsx,.xlsm" onChange={(event) => uploadSide(side,event)}/><UploadCloud/><strong>Choose Excel or CSV</strong><span>Copied and SHA-256 fingerprinted</span></label>{discovery && <div className="tag-row"><span>{discovery.tables[0].row_count_estimate} rows</span><span>{discovery.tables[0].columns.length} fields</span><span>{discovery.tables[0].sheet_name}</span></div>}</section>; })}
    </div>
    {leftDiscovery && rightDiscovery && <>
      <div className="builder-grid"><section className="panel"><div className="panel-title"><div><span className="eyebrow">KEY DEFINITION</span><h3>Canonical business key</h3></div><Fingerprint/></div><label>Search fields<div className="search-input"><Search size={16}/><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name or type"/></div></label><label>Business key<select value={keyField} onChange={(event) => { setKeyField(event.target.value); setPreview(null); }}><option value="">Select common field</option>{filteredFields.map((field) => <option key={field.source_name} value={field.source_name}>{field.source_name} · {field.inferred_type}</option>)}</select></label><div className="warning-note"><ShieldCheck size={16}/>Row position is never used unless selected as a canonical field.</div></section><section className="panel wide"><div className="panel-title"><div><span className="eyebrow">STRUCTURE COMPARISON</span><h3>{structureDifferences.length} schema differences</h3></div><GitCompareArrows/></div><DataTable rows={structureDifferences} empty="Structures are compatible; field order alone is non-breaking."/></section></div>
      <section className="panel"><div className="panel-title"><div><span className="eyebrow">COMPARISON FIELD SELECTION</span><h3>Choose field-level evidence</h3></div><FileSearch/></div><div className="field-chip-grid">{filteredFields.map((field) => <label className="check-line field-chip" key={field.source_name}><input type="checkbox" checked={comparisonFields.includes(field.source_name)} onChange={(event) => setComparisonFields(event.target.checked ? [...comparisonFields,field.source_name] : comparisonFields.filter((item) => item !== field.source_name))}/><span><strong>{field.source_name}</strong><small>{field.inferred_type}</small></span></label>)}</div></section>
      <div className="builder-grid"><section className="panel"><div className="panel-title"><div><span className="eyebrow">NORMALISATION BUILDER</span><h3>Before / after key preview</h3></div><SlidersHorizontal/></div><label>Pipeline<select value={normalisation} onChange={(event) => setNormalisation(event.target.value)}><option value="trim_lower">Trim · collapse · lowercase</option><option value="trim_upper">Trim · collapse · uppercase</option><option value="punctuation">Trim · remove punctuation · lowercase</option></select></label><div className="normalisation-preview"><span>ORIGINAL</span><code>{normalisationSample}</code><span>NORMALISED</span><code>{normalisePreview(normalisationSample,normalisation)}</code></div><small>Original evidence is retained; each operation emits audit metadata.</small></section><section className="panel wide"><div className="panel-title"><div><span className="eyebrow">ORDERED STAGE BUILDER</span><h3>Drag, move, or remove stages</h3></div><Settings2/></div><div className="stage-toolbar">{(["exact","normalised_exact","numeric_tolerance","date_tolerance","fuzzy_text","weighted_multi_field"] as MatchMethod[]).map((method) => <button className="chip-button" key={method} onClick={() => addStage(method)}><Plus size={14}/>{methodLabels[method]}</button>)}</div><div className="step-stack">{stages.map((item,index) => <article className="operation-row stage-row" draggable onDragStart={() => setDragIndex(index)} onDragOver={(event) => event.preventDefault()} onDrop={() => dropStage(index)} key={item.id}><GripVertical className="drag-handle"/><span className="stage-priority">{index+1}</span><div><strong>{item.name}</strong><span>{methodLabels[item.method]} · one-to-one · remove matches</span></div><StatusChip value={item.method.includes("fuzzy") ? "review-aware" : "deterministic"}/><button className="icon-button" onClick={() => moveStage(index,-1)} aria-label={`Move ${item.name} up`}><ArrowUp/></button><button className="icon-button" onClick={() => moveStage(index,1)} aria-label={`Move ${item.name} down`}><ArrowDown/></button><button className="icon-button" onClick={() => setStages(stages.filter((_,position) => position !== index))} aria-label={`Remove ${item.name}`}><Trash2/></button></article>)}</div></section></div>
      <div className="configuration-grid"><section className="panel"><span className="eyebrow">NUMERIC TOLERANCE</span><label>Field<select value={numericField} onChange={(event) => setNumericField(event.target.value)}>{commonFields.map((field) => <option key={field.source_name}>{field.source_name}</option>)}</select></label><label>Absolute tolerance<input type="number" min="0" step="0.01" value={numericTolerance} onChange={(event) => setNumericTolerance(event.target.value)}/></label><small>Decimal-safe; negative and zero values remain explicit.</small></section><section className="panel"><span className="eyebrow">DATE TOLERANCE</span><label>Field<select value={dateField} onChange={(event) => setDateField(event.target.value)}>{commonFields.map((field) => <option key={field.source_name}>{field.source_name}</option>)}</select></label><label>Calendar days<input type="number" min="0" value={dateTolerance} onChange={(event) => setDateTolerance(Number(event.target.value))}/></label><small>Business days require a configured calendar.</small></section><section className="panel"><span className="eyebrow">FUZZY SAFETY</span><label>Text field<select value={fuzzyField} onChange={(event) => setFuzzyField(event.target.value)}>{commonFields.map((field) => <option key={field.source_name}>{field.source_name}</option>)}</select></label><label>Blocking field<select value={blockField} onChange={(event) => setBlockField(event.target.value)}>{commonFields.map((field) => <option key={field.source_name}>{field.source_name}</option>)}</select></label><label>Minimum threshold<input type="number" min="0.7" max="1" step="0.01" value={fuzzyThreshold} onChange={(event) => setFuzzyThreshold(event.target.value)}/></label></section><section className="panel"><span className="eyebrow">WEIGHTED SCORE</span><div className="weight-row"><span>Text similarity</span><strong>60%</strong></div><div className="weight-bar"><span style={{width:"60%"}}/></div><div className="weight-row"><span>Blocking evidence</span><strong>40%</strong></div><div className="weight-bar"><span style={{width:"40%"}}/></div><small>Every field score and contribution remains visible.</small></section></div>
      <section className="panel safety-panel"><div className="panel-title"><div><span className="eyebrow">CANDIDATE ESTIMATE & SAFETY</span><h3>{preview ? `${preview.stage_estimates.reduce((sum,item) => sum+item.estimated_pairs,0).toLocaleString()} candidate pairs` : "Preview to calculate candidate volume"}</h3></div><ShieldCheck/></div>{preview ? <div className="candidate-estimates">{preview.stage_estimates.map((item) => <article key={item.stage_id}><strong>{item.stage_id}</strong><span>{item.estimated_pairs.toLocaleString()} / {item.maximum_pairs.toLocaleString()}</span><StatusChip value={item.blocked ? "blocked" : "within budget"}/></article>)}</div> : <div className="warning-note"><AlertTriangle/>Fuzzy stages require blocking. The engine stops before the maximum candidate limit.</div>}<button className="secondary-button" disabled={!keyField || !stages.length} onClick={previewWorkflow}><Eye/>Preview execution</button></section>
    </>}
    {preview && <><section className="metrics-grid"><MetricCard icon={CheckCircle2} label="Matched" value={preview.summary.matched} note={`${preview.summary.exact_matches} exact`} tone="success"/><MetricCard icon={Scale} label="Tolerance" value={preview.summary.tolerance_matches} note={`${preview.summary.fuzzy_matches} fuzzy`}/><MetricCard icon={AlertTriangle} label="Review" value={preview.summary.review_pending} note="Ambiguous candidates" tone={preview.summary.review_pending ? "warning" : "success"}/><MetricCard icon={Layers3} label="Unmatched" value={preview.summary.left_unmatched+preview.summary.right_unmatched} note="Left + right"/></section><div className="tabbed-results"><section className="panel"><div className="panel-title"><div><span className="eyebrow">MATCH PREVIEW</span><h3>Stage, score, reason and lineage</h3></div><GitCompareArrows/></div><DataTable rows={preview.matches as unknown as Record<string,unknown>[]} empty="No preview matches."/></section><section className="panel"><div className="panel-title"><div><span className="eyebrow">FIELD DIFFERENCES</span><h3>Left and right evidence</h3></div><FileSearch/></div><DataTable rows={preview.field_differences} empty="No field differences in preview."/></section></div><section className="panel execution-panel"><div className="panel-title"><div><span className="eyebrow">LIVE RECONCILIATION PROGRESS</span><h3>{job?.current_operation?.replaceAll("_"," ") ?? "Ready for background execution"}</h3></div><StatusChip value={job?.status ?? "previewed"}/></div><div className="job-progress-track"><span style={{width:`${job?.progress_percent ?? 0}%`}}/></div><div className="panel-footer"><span>{job ? `${job.rows_processed} rows processed · output ${job.output_available ? "published" : "isolated"}` : "Full runs checkpoint between matching stages."}</span>{job && ["queued","running"].includes(job.status) ? <button className="secondary-button" onClick={() => void api.cancelReconciliationJob(job.id).then(setJob)}><X/>Cancel safely</button> : <button className="primary-button" onClick={executeWorkflow}><Play/>Execute full reconciliation</button>}</div></section></>}
    {runRecord && <><section className="panel"><div className="panel-title"><div><span className="eyebrow">RECONCILIATION SUMMARY</span><h3>{runRecord.status} · {runRecord.summary.matched} matches</h3></div><CheckCircle2/></div><section className="metrics-grid"><MetricCard icon={Database} label="Left" value={runRecord.summary.total_left_rows} note={`${runRecord.summary.left_unmatched} unmatched`}/><MetricCard icon={Database} label="Right" value={runRecord.summary.total_right_rows} note={`${runRecord.summary.right_unmatched} unmatched`}/><MetricCard icon={Scale} label="Matched" value={runRecord.summary.matched} note="Across all stages" tone="success"/><MetricCard icon={AlertTriangle} label="Review" value={runRecord.summary.review_pending} note="Pending decisions" tone="warning"/></section></section><section className="panel"><div className="panel-title"><div><span className="eyebrow">MANUAL REVIEW QUEUE</span><h3>{reviews.length} review items</h3></div><Search/></div>{reviews.length ? <div className="review-grid">{reviews.map((item) => <button key={item.id} onClick={() => openReview(item)}><div><strong>{item.match_stage_id}</strong><span>{item.review_reason}</span></div><StatusChip value={item.status}/><Eye/></button>)}</div> : <div className="empty-state compact"><CheckCircle2/><strong>No manual review required</strong><span>All accepted matches passed policy and cardinality gates.</span></div>}</section></>}
    {selectedReview && <section className="candidate-drawer" role="dialog" aria-modal="true" aria-label="Candidate comparison"><div className="drawer-head"><div><span className="eyebrow">CANDIDATE COMPARISON</span><h2>{selectedReview.match_stage_id}</h2></div><button className="icon-button" onClick={() => setSelectedReview(null)} aria-label="Close candidate drawer"><X/></button></div><div className="candidate-columns"><section><h3>Left evidence</h3><DataTable rows={[selectedReview.left_record]} empty="Left evidence unavailable."/></section><section><h3>Right candidates</h3><DataTable rows={selectedReview.right_candidates} empty="No candidate evidence."/></section></div><div className="decision-actions"><button onClick={() => decide(selectedReview,"approve_suggested_match")}><CheckCircle2/>Approve suggested</button><button onClick={() => decide(selectedReview,"approve_alternate_candidate")}><Scale/>Approve alternate</button><button onClick={() => decide(selectedReview,"reject_all_candidates")}><X/>Reject all</button><button onClick={() => decide(selectedReview,"defer")}><AlertTriangle/>Defer</button><button onClick={() => decide(selectedReview,"escalate")}><ArrowUp/>Escalate</button></div><section className="panel decision-history"><span className="eyebrow">IMMUTABLE DECISION HISTORY</span><DataTable rows={decisionHistory} empty="No decisions recorded for this item."/></section></section>}
    {manifest && <section className="panel"><div className="panel-title"><div><span className="eyebrow">EXPORT & EVIDENCE PACKAGE</span><h3>{manifest.entries.length} fingerprinted outputs</h3></div><FileOutput/></div><div className="source-grid">{manifest.entries.map((entry) => <article key={entry.relative_path}><div className="file-icon"><FileOutput/></div><div><strong>{entry.relative_path}</strong><span>{entry.classification} · {entry.row_count} rows</span><small>{entry.sha256.slice(0,20)}…</small></div></article>)}</div>{run && zipIndex >= 0 && <a className="primary-button export-button" href={api.artifactUrl(run.id,zipIndex)}><Download/>Open deterministic ZIP package</a>}</section>}
  </>;
}

function normalisationPipeline(kind: string): Record<string, unknown> {
  const operations = kind === "trim_upper"
    ? ["text.trim_whitespace","text.collapse_spaces","text.uppercase"]
    : kind === "punctuation"
      ? ["text.trim_whitespace","text.remove_punctuation","text.lowercase"]
      : ["text.trim_whitespace","text.collapse_spaces","text.lowercase"];
  return { schema_version: "2b.1", version: 1, operations: operations.map((operation_id) => ({ operation_id, operation_version: 1, parameters: {}, enabled: true })), preserve_original: true };
}

function normalisePreview(value: string, kind: string) {
  let output = value.trim().replace(/\s+/g," ");
  if (kind === "punctuation") output = output.replace(/[^\p{L}\p{N}\s]/gu,"");
  return kind === "trim_upper" ? output.toUpperCase() : output.toLowerCase();
}

function messageOf(reason: unknown) {
  return reason instanceof Error ? reason.message.replace(/^\{"detail":"?|"?\}$/g, "") : "Unexpected local error";
}
