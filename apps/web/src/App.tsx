import {
  Activity, AlertTriangle, ArrowRight, Check, CheckCircle2, ChevronRight, CircleDot,
  Clock3, Database, Download, FileOutput, FileSearch, Fingerprint, FolderPlus, History,
  Layers3, LoaderCircle, Map as MapIcon, Menu, Play, Plus, Save, Settings2, ShieldCheck,
  SlidersHorizontal, Sparkles, Table2, UploadCloud, WandSparkles, X, XCircle,
} from "lucide-react";
import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { api } from "./api";
import { DataTable } from "./components/DataTable";
import { MetricCard } from "./components/MetricCard";
import { StatusChip } from "./components/StatusChip";
import type {
  CanonicalField, ColumnMapping, DiscoveryResult, OperationNode, PreviewResult, Project,
  RunRecord, SourceHandle, TableDiscovery, ValidationRule, Workflow,
} from "./types";

const stages = [
  { id: "workspace", label: "Workspace", icon: Layers3 },
  { id: "import", label: "Import dataset", icon: UploadCloud },
  { id: "inspect", label: "Source inspection", icon: FileSearch },
  { id: "profile", label: "Column profile", icon: Activity },
  { id: "mapping", label: "Column mapping", icon: MapIcon },
  { id: "cleaning", label: "Cleaning steps", icon: WandSparkles },
  { id: "validation", label: "Validation rules", icon: ShieldCheck },
  { id: "preview", label: "Run preview", icon: Play },
  { id: "results", label: "Results & export", icon: FileOutput },
  { id: "history", label: "Run history", icon: History },
] as const;

type Stage = (typeof stages)[number]["id"];

const operations = [
  ["text.trim", "Trim whitespace"], ["text.normalise_spaces", "Normalise spaces"],
  ["text.uppercase", "Uppercase"], ["text.lowercase", "Lowercase"],
  ["text.proper_case", "Proper case"], ["text.remove_non_printable", "Remove non-printable"],
  ["text.normalise_nulls", "Normalise null-like values"], ["row.remove_blank", "Remove blank rows"],
] as const;

function slugify(label: string) {
  const value = label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "field";
  return /^\d/.test(value) ? `field_${value}` : value;
}

function App() {
  const [stage, setStage] = useState<Stage>("workspace");
  const [project, setProject] = useState<Project | null>(null);
  const [source, setSource] = useState<SourceHandle | null>(null);
  const [discovery, setDiscovery] = useState<DiscoveryResult | null>(null);
  const [table, setTable] = useState<TableDiscovery | null>(null);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [run, setRun] = useState<RunRecord | null>(null);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => { void refreshRuns(); }, [project?.id]);

  async function refreshRuns() {
    try { setRuns(await api.listRuns(project?.id)); } catch { setRuns([]); }
  }

  function canVisit(target: Stage) {
    if (["workspace", "import", "history"].includes(target)) return true;
    if (["inspect", "profile"].includes(target)) return Boolean(discovery);
    if (["mapping", "cleaning", "validation", "preview"].includes(target)) return Boolean(workflow);
    return Boolean(run);
  }

  function navigate(target: Stage) {
    if (!canVisit(target)) return;
    setStage(target); setSidebarOpen(false); setError(null);
  }

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy("Creating secure local workspace…"); setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const created = await api.createProject(String(form.get("name") || "Untitled project"));
      setProject(created); setStage("import");
    } catch (reason) { setError(messageOf(reason)); } finally { setBusy(null); }
  }

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; if (!file || !project) return;
    setBusy("Fingerprinting and inspecting source…"); setError(null); setPreview(null); setRun(null);
    try {
      const uploaded = await api.uploadSource(project.id, file);
      const inspected = await api.discover(uploaded.id);
      setSource(uploaded); setDiscovery(inspected);
      const selected = inspected.tables.find((candidate) => candidate.sheet_state === "visible") ?? inspected.tables[0];
      if (!selected) throw new Error("No usable table was found in this source.");
      setTable(selected); setWorkflow(buildWorkflow(project, uploaded, selected)); setStage("inspect");
    } catch (reason) { setError(messageOf(reason)); } finally { setBusy(null); event.target.value = ""; }
  }

  async function rediscover(sheetName: string, headerRow: number | null = null) {
    if (!source || !project) return; setBusy("Applying discovery override…"); setError(null);
    try {
      const inspected = await api.discover(source.id, sheetName, headerRow);
      const selected = inspected.tables.find((candidate) => candidate.sheet_name === sheetName) ?? inspected.tables[0];
      setDiscovery(inspected); setTable(selected); setWorkflow(buildWorkflow(project, source, selected));
    } catch (reason) { setError(messageOf(reason)); } finally { setBusy(null); }
  }

  function updateCanonical(index: number, id: string) {
    if (!workflow) return; const nextId = slugify(id);
    const oldId = workflow.mapping.canonical_fields[index].id;
    setWorkflow({
      ...workflow,
      mapping: {
        ...workflow.mapping,
        canonical_fields: workflow.mapping.canonical_fields.map((field, item) => item === index ? { ...field, id: nextId } : field),
        mappings: workflow.mapping.mappings.map((mapping) => mapping.canonical_field_id === oldId ? { ...mapping, canonical_field_id: nextId } : mapping),
      },
      operations: workflow.operations.map((node) => node.config.field_id === oldId ? { ...node, config: { ...node.config, field_id: nextId } } : node),
      validation_rules: workflow.validation_rules.map((rule) => rule.field_id === oldId ? { ...rule, field_id: nextId } : rule),
      updated_at: new Date().toISOString(),
    });
  }

  function addOperation(operationId: string, fieldId: string) {
    if (!workflow) return;
    const config = operationId === "row.remove_blank" ? {} : { field_id: fieldId };
    setWorkflow({ ...workflow, operations: [...workflow.operations, { id: crypto.randomUUID(), operation_id: operationId, operation_version: 1, config, enabled: true }], updated_at: new Date().toISOString() });
  }

  function removeOperation(id: string) {
    if (workflow) setWorkflow({ ...workflow, operations: workflow.operations.filter((node) => node.id !== id), updated_at: new Date().toISOString() });
  }

  function addRule(ruleType: ValidationRule["rule_type"], fieldId: string) {
    if (!workflow) return; const stamp = workflow.validation_rules.length + 1;
    const configs: Record<ValidationRule["rule_type"], Record<string, unknown>> = {
      required: {}, data_type: { data_type: "text" }, unique: {}, allowed_values: { values: ["active", "inactive"] },
      min_max: { min: 0, max: 100 }, text_length: { min: 1, max: 120 }, regex: { pattern: ".+" },
    };
    const rule: ValidationRule = { id: `RULE_${stamp}`, rule_type: ruleType, field_id: fieldId, severity: "error", reason_code: `${fieldId.toUpperCase()}_${ruleType.toUpperCase()}_FAILED`, message: `${fieldId.replaceAll("_", " ")} failed ${ruleType.replaceAll("_", " ")} validation`, config: configs[ruleType] };
    setWorkflow({ ...workflow, validation_rules: [...workflow.validation_rules, rule], updated_at: new Date().toISOString() });
  }

  async function saveAndPreview() {
    if (!source || !workflow) return; setBusy("Validating workflow and preparing bounded preview…"); setError(null);
    try { await api.saveWorkflow(workflow); setPreview(await api.preview(source.id, workflow)); setStage("preview"); }
    catch (reason) { setError(messageOf(reason)); } finally { setBusy(null); }
  }

  async function execute() {
    if (!source || !workflow) return; setBusy("Executing in an isolated run directory…"); setError(null);
    try { const record = await api.run(source.id, workflow); setRun(record); await refreshRuns(); setStage("results"); }
    catch (reason) { setError(messageOf(reason)); } finally { setBusy(null); }
  }

  const progress = Math.round(((stages.findIndex((item) => item.id === stage) + 1) / stages.length) * 100);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace-main">Skip to workspace</a>
      <aside className={sidebarOpen ? "sidebar open" : "sidebar"} aria-label="Workspace navigation">
        <div className="brand"><div className="brand-mark"><Sparkles size={20} /></div><div><strong>DataPilot</strong><span>STUDIO</span></div><button className="mobile-close" onClick={() => setSidebarOpen(false)} aria-label="Close navigation"><X /></button></div>
        <div className="project-context"><span>LOCAL WORKSPACE</span><strong>{project?.name ?? "No project selected"}</strong><small><ShieldCheck size={13} /> Files stay on this device</small></div>
        <nav>
          <p className="nav-label">GUIDED WORKFLOW</p>
          {stages.map(({ id, label, icon: Icon }, index) => (
            <button key={id} className={stage === id ? "nav-item active" : "nav-item"} disabled={!canVisit(id)} onClick={() => navigate(id)}>
              <span className="nav-index">{canVisit(id) && stages.findIndex((item) => item.id === stage) > index ? <Check size={13} /> : index + 1}</span><Icon size={17} /><span>{label}</span>{stage === id && <ChevronRight size={15} />}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot"><ShieldCheck size={16} /><div><strong>Immutable source mode</strong><span>SHA-256 verified each run</span></div></div>
      </aside>
      {sidebarOpen && <button className="scrim" onClick={() => setSidebarOpen(false)} aria-label="Close navigation overlay" />}
      <div className="main-column">
        <header className="topbar">
          <button className="menu-button" onClick={() => setSidebarOpen(true)} aria-label="Open navigation"><Menu /></button>
          <div><span className="eyebrow">DATA AUTOMATION WORKSPACE</span><strong>{stages.find((item) => item.id === stage)?.label}</strong></div>
          <div className="topbar-actions"><span className="local-badge"><CircleDot size={14} /> Local only</span><div className="avatar" aria-label="Local user">AT</div></div>
        </header>
        <div className="progress-track" aria-label={`${progress}% through guided workflow`}><span style={{ width: `${progress}%` }} /></div>
        <main id="workspace-main">
          {busy && <div className="busy-banner" role="status"><LoaderCircle className="spin" size={18} />{busy}</div>}
          {error && <div className="error-banner" role="alert"><XCircle size={19} /><div><strong>Action could not be completed</strong><span>{error}</span></div><button onClick={() => setError(null)} aria-label="Dismiss error"><X size={17} /></button></div>}
          {stage === "workspace" && <WorkspaceScreen project={project} runs={runs} onCreate={createProject} onContinue={() => setStage("import")} />}
          {stage === "import" && <ImportScreen project={project} source={source} onCreate={createProject} onUpload={upload} onContinue={() => discovery && setStage("inspect")} />}
          {stage === "inspect" && discovery && table && <InspectScreen discovery={discovery} table={table} onSelect={rediscover} onContinue={() => setStage("profile")} />}
          {stage === "profile" && table && <ProfileScreen table={table} onContinue={() => setStage("mapping")} />}
          {stage === "mapping" && workflow && table && <MappingScreen workflow={workflow} table={table} onUpdate={updateCanonical} onContinue={() => setStage("cleaning")} />}
          {stage === "cleaning" && workflow && <CleaningScreen workflow={workflow} onAdd={addOperation} onRemove={removeOperation} onContinue={() => setStage("validation")} />}
          {stage === "validation" && workflow && <ValidationScreen workflow={workflow} onAdd={addRule} onRemove={(id) => setWorkflow({ ...workflow, validation_rules: workflow.validation_rules.filter((rule) => rule.id !== id) })} onPreview={saveAndPreview} />}
          {stage === "preview" && preview && workflow && <PreviewScreen preview={preview} workflow={workflow} onExecute={execute} />}
          {stage === "results" && run && <ResultsScreen run={run} onHistory={() => setStage("history")} />}
          {stage === "history" && <HistoryScreen runs={runs} />}
        </main>
      </div>
    </div>
  );
}

function ScreenHead({ eyebrow, title, description, step }: { eyebrow: string; title: string; description: string; step: string }) {
  return <div className="screen-head"><div><span className="eyebrow teal">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div><span className="step-pill">{step}</span></div>;
}

function WorkspaceScreen({ project, runs, onCreate, onContinue }: { project: Project | null; runs: RunRecord[]; onCreate: (event: FormEvent<HTMLFormElement>) => void; onContinue: () => void }) {
  return <>
    <ScreenHead eyebrow="PRODUCT FOUNDATION" title="Turn changing data into reliable outputs." description="Discover structure, apply reusable rules, and export audit-ready workbooks without changing the original file." step="Workspace" />
    <section className="metrics-grid">
      <MetricCard icon={Layers3} label="Projects" value={project ? 1 : 0} note="Portable local workspaces" />
      <MetricCard icon={History} label="Workflow runs" value={runs.length} note="Every result is traceable" />
      <MetricCard icon={ShieldCheck} label="Source overwrites" value="0" note="Immutable by design" tone="success" />
      <MetricCard icon={Activity} label="Run health" value={runs.length ? `${Math.round(runs.filter((item) => item.status === "succeeded").length / runs.length * 100)}%` : "—"} note="Successful full runs" />
    </section>
    <div className="workspace-grid">
      <section className="panel hero-panel"><div className="hero-orbit"><Database size={42} /></div><span className="eyebrow teal">START A DYNAMIC WORKFLOW</span><h2>Teach the process once.<br/><em>Reuse it when the file changes.</em></h2><p>DataPilot maps changing source labels to stable canonical fields before any rule executes.</p>
        {project ? <button className="primary-button" onClick={onContinue}>Continue with {project.name}<ArrowRight size={17} /></button> : <form className="inline-form" onSubmit={onCreate}><label><span>Project name</span><input name="name" required minLength={2} maxLength={120} defaultValue="My data quality workspace" /></label><button className="primary-button" type="submit"><FolderPlus size={17} />Create local project</button></form>}
        <div className="trust-row"><span><Fingerprint />Source fingerprint</span><span><EyeIcon />Preview first</span><span><FileOutput />Isolated output</span></div>
      </section>
      <section className="panel"><div className="panel-title"><div><span className="eyebrow">RECENT ACTIVITY</span><h3>Run history</h3></div><Clock3 size={20} /></div>{runs.length ? runs.slice(0, 4).map((item) => <div className="activity-row" key={item.id}><div className="file-icon"><FileOutput size={17} /></div><div><strong>{item.source_filename}</strong><span>{item.rows_read.toLocaleString()} rows · {item.duration_ms} ms</span></div><StatusChip value={item.status} /></div>) : <div className="empty-state compact"><History size={25} /><strong>No runs yet</strong><span>Your first audited run will appear here.</span></div>}</section>
    </div>
  </>;
}

function EyeIcon() { return <FileSearch />; }

function ImportScreen({ project, source, onCreate, onUpload, onContinue }: { project: Project | null; source: SourceHandle | null; onCreate: (event: FormEvent<HTMLFormElement>) => void; onUpload: (event: ChangeEvent<HTMLInputElement>) => void; onContinue: () => void }) {
  if (!project) return <><ScreenHead eyebrow="PROJECT REQUIRED" title="Create a local project first." description="Projects keep workflows, mappings, and run evidence organised without embedding source data." step="1 of 9"/><section className="panel narrow"><form className="stack-form" onSubmit={onCreate}><label>Project name<input name="name" required defaultValue="My data quality workspace" /></label><button className="primary-button" type="submit">Create project<ArrowRight size={17}/></button></form></section></>;
  return <><ScreenHead eyebrow="SAFE INGESTION" title="Import a dataset." description="Supported now: CSV, XLSX, and XLSM inspection. The source is copied, fingerprinted, and never overwritten." step="1 of 9"/><section className="panel upload-panel"><label className="drop-zone"><input type="file" accept=".csv,.xlsx,.xlsm" onChange={onUpload}/><div className="upload-mark"><UploadCloud size={30}/></div><strong>Choose an Excel or CSV file</strong><span>or drop it here · arbitrary row and column counts</span><small>Maximum size is governed by local resources in this milestone.</small></label>{source && <div className="source-receipt"><div className="file-icon large"><Table2/></div><div><strong>{source.original_filename}</strong><span>{(source.size_bytes / 1024).toFixed(1)} KB · SHA-256 verified</span><code>{source.sha256.slice(0, 20)}…</code></div><CheckCircle2 className="success-icon"/><button className="primary-button" onClick={onContinue}>Inspect source<ArrowRight size={17}/></button></div>}</section></>;
}

function InspectScreen({ discovery, table, onSelect, onContinue }: { discovery: DiscoveryResult; table: TableDiscovery; onSelect: (sheet: string, row: number | null) => void; onContinue: () => void }) {
  return <><ScreenHead eyebrow="DYNAMIC DISCOVERY" title="Review what DataPilot found." description="Every sheet and header decision is metadata. Accept the suggestion or override it before processing." step="2 of 9"/><section className="metrics-grid three"><MetricCard icon={Table2} label="Candidate sheets" value={discovery.tables.length} note="Visible and hidden reported"/><MetricCard icon={Database} label="Estimated rows" value={table.row_count_estimate.toLocaleString()} note={`${table.column_count} discovered columns`}/><MetricCard icon={Sparkles} label="Discovery confidence" value={`${Math.round(table.confidence * 100)}%`} note="Heuristic, always overrideable" tone={table.confidence > .7 ? "success" : "warning"}/></section><div className="split-grid"><section className="panel"><div className="panel-title"><div><span className="eyebrow">SOURCE STRUCTURE</span><h3>Sheet and header</h3></div><Settings2/></div><label>Sheet<select value={table.sheet_name} onChange={(event) => void onSelect(event.target.value, null)}>{discovery.tables.map((item) => <option key={item.table_id} value={item.sheet_name}>{item.sheet_name} ({item.sheet_state})</option>)}</select></label><div className="candidate-list">{table.candidate_headers.map((candidate) => <button key={candidate.row_number} className={candidate.row_number === table.selected_header_row ? "candidate selected" : "candidate"} onClick={() => void onSelect(table.sheet_name, candidate.row_number)}><span className="radio-dot"/><div><strong>Row {candidate.row_number}</strong><span>{candidate.labels.filter(Boolean).slice(0,3).join(" · ")}</span><small>{candidate.evidence.join(" · ")}</small></div><b>{Math.round(candidate.confidence * 100)}%</b></button>)}</div>{table.warnings.map((warning) => <div className="warning-note" key={warning}><AlertTriangle size={16}/>{warning}</div>)}</section><section className="panel wide"><div className="panel-title"><div><span className="eyebrow">BOUNDED PREVIEW</span><h3>{table.sheet_name}</h3></div><StatusChip value={table.sheet_state}/></div><DataTable rows={table.preview} empty="No preview rows were found."/><div className="panel-footer"><span>Candidate region {table.candidate_region}</span><button className="primary-button" onClick={onContinue}>Review profiles<ArrowRight size={17}/></button></div></section></div></>;
}

function ProfileScreen({ table, onContinue }: { table: TableDiscovery; onContinue: () => void }) {
  return <><ScreenHead eyebrow="SCHEMA INTELLIGENCE" title="Understand every column before changing it." description="Types and semantic roles are suggestions. Mixed values and ambiguous dates stay visible rather than being silently coerced." step="3 of 9"/><section className="profile-grid">{table.columns.map((column) => <article className="profile-card" key={column.source_name}><div><span className="type-icon">{column.inferred_type.slice(0,1).toUpperCase()}</span><div><strong>{column.source_name}</strong><span>{column.inferred_type}</span></div>{column.is_key_candidate && <span className="mini-pill">Key candidate</span>}</div><div className="profile-stats"><span><b>{column.null_percentage}%</b> null</span><span><b>{column.unique_count}</b> unique</span><span><b>{column.duplicate_count}</b> duplicate</span></div><div className="sample-values">{column.sample_values.slice(0,3).map((value) => <code key={value}>{value}</code>)}</div>{column.semantic_roles.length > 0 && <div className="tag-row">{column.semantic_roles.map((role) => <span key={role}>{role}</span>)}</div>}{column.warnings.map((warning) => <small className="column-warning" key={warning}><AlertTriangle size={13}/>{warning}</small>)}</article>)}</section><div className="sticky-action"><div><strong>{table.columns.length} columns profiled</strong><span>Review canonical names next</span></div><button className="primary-button" onClick={onContinue}>Map columns<ArrowRight size={17}/></button></div></>;
}

function MappingScreen({ workflow, table, onUpdate, onContinue }: { workflow: Workflow; table: TableDiscovery; onUpdate: (index: number, id: string) => void; onContinue: () => void }) {
  return <><ScreenHead eyebrow="CANONICAL SCHEMA" title="Separate source labels from reusable logic." description="Downstream steps use canonical IDs. Reordering the source will not change the workflow." step="4 of 9"/><section className="panel"><div className="mapping-head"><span>Source column</span><span>Canonical field ID</span><span>Type</span><span>Confidence</span></div>{workflow.mapping.canonical_fields.map((field, index) => { const mapping = workflow.mapping.mappings[index]; const profile = table.columns[index]; return <div className="mapping-row" key={mapping.source_column ?? field.id}><div><Table2 size={16}/><div><strong>{mapping.source_column}</strong><span>{profile?.sample_values.slice(0,2).join(" · ")}</span></div></div><div className="mapping-arrow"><ArrowRight size={16}/></div><label className="sr-label">Canonical ID<input aria-label={`Canonical ID for ${mapping.source_column}`} value={field.id} onChange={(event) => onUpdate(index, event.target.value)}/></label><StatusChip value={field.data_type}/><span className="confidence"><CheckCircle2 size={15}/>{Math.round(mapping.confidence * 100)}%</span></div>})}</section><div className="sticky-action"><div><strong>{workflow.mapping.mappings.length} mappings ready</strong><span>Source labels stay at the connector boundary</span></div><button className="primary-button" onClick={onContinue}>Configure cleaning<ArrowRight size={17}/></button></div></>;
}

function CleaningScreen({ workflow, onAdd, onRemove, onContinue }: { workflow: Workflow; onAdd: (op: string, field: string) => void; onRemove: (id: string) => void; onContinue: () => void }) {
  const [operationId, setOperationId] = useState<string>("text.trim"); const [field, setField] = useState(workflow.mapping.canonical_fields[0]?.id ?? "");
  return <><ScreenHead eyebrow="DETERMINISTIC CLEANING" title="Build an ordered cleaning recipe." description="Each step is versioned, previewable, and reports affected rows. Add at least three to prove the reusable operation stack." step="5 of 9"/><div className="builder-grid"><section className="panel"><div className="panel-title"><div><span className="eyebrow">OPERATION LIBRARY</span><h3>Add a cleaning step</h3></div><Plus/></div><label>Operation<select value={operationId} onChange={(event) => setOperationId(event.target.value)}>{operations.map(([id,label]) => <option value={id} key={id}>{label}</option>)}</select></label>{operationId !== "row.remove_blank" && <label>Canonical field<select value={field} onChange={(event) => setField(event.target.value)}>{workflow.mapping.canonical_fields.map((item) => <option value={item.id} key={item.id}>{item.label} · {item.id}</option>)}</select></label>}<button className="secondary-button full" onClick={() => onAdd(operationId, field)}><Plus size={17}/>Add to recipe</button></section><section className="panel wide"><div className="panel-title"><div><span className="eyebrow">ORDERED RECIPE</span><h3>{workflow.operations.length} cleaning steps</h3></div><SlidersHorizontal/></div>{workflow.operations.length ? <div className="step-stack">{workflow.operations.map((node,index) => <div className="operation-row" key={node.id}><span className="drag-handle">{index + 1}</span><div className="operation-icon"><WandSparkles size={17}/></div><div><strong>{operations.find(([id]) => id === node.operation_id)?.[1] ?? node.operation_id}</strong><span>{String(node.config.field_id ?? "All canonical fields")} · v{node.operation_version}</span></div><StatusChip value="ready"/><button className="icon-button" onClick={() => onRemove(node.id)} aria-label={`Remove ${node.operation_id}`}><X size={16}/></button></div>)}</div> : <div className="empty-state"><WandSparkles/><strong>No cleaning steps yet</strong><span>Add three reusable operations to continue.</span></div>}</section></div><div className="sticky-action"><div><strong>{workflow.operations.length} configured steps</strong><span>{workflow.operations.length < 3 ? `${3-workflow.operations.length} more recommended for acceptance` : "Vertical-slice minimum reached"}</span></div><button className="primary-button" disabled={workflow.operations.length < 3} onClick={onContinue}>Configure validation<ArrowRight size={17}/></button></div></>;
}

function ValidationScreen({ workflow, onAdd, onRemove, onPreview }: { workflow: Workflow; onAdd: (type: ValidationRule["rule_type"], field: string) => void; onRemove: (id: string) => void; onPreview: () => void }) {
  const [type,setType] = useState<ValidationRule["rule_type"]>("required"); const [field,setField] = useState(workflow.mapping.canonical_fields[0]?.id ?? "");
  return <><ScreenHead eyebrow="QUALITY GATES" title="Make invalid data explain itself." description="Every finding includes row, field, rule, severity, reason code, message, and original value." step="6 of 9"/><div className="builder-grid"><section className="panel"><div className="panel-title"><div><span className="eyebrow">RULE LIBRARY</span><h3>Add validation</h3></div><Plus/></div><label>Rule type<select value={type} onChange={(event) => setType(event.target.value as ValidationRule["rule_type"])}>{["required","data_type","unique","allowed_values","min_max","text_length","regex"].map((item) => <option value={item} key={item}>{item.replaceAll("_"," ")}</option>)}</select></label><label>Canonical field<select value={field} onChange={(event) => setField(event.target.value)}>{workflow.mapping.canonical_fields.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label><button className="secondary-button full" onClick={() => onAdd(type,field)}><Plus size={17}/>Add validation rule</button></section><section className="panel wide"><div className="panel-title"><div><span className="eyebrow">VALIDATION POLICY</span><h3>{workflow.validation_rules.length} active rules</h3></div><ShieldCheck/></div>{workflow.validation_rules.length ? <div className="step-stack">{workflow.validation_rules.map((rule) => <div className="operation-row" key={rule.id}><div className="operation-icon validation"><CheckCircle2 size={17}/></div><div><strong>{rule.rule_type.replaceAll("_"," ")} · {rule.field_id}</strong><span>{rule.reason_code}</span></div><StatusChip value={rule.severity}/><button className="icon-button" onClick={() => onRemove(rule.id)} aria-label={`Remove ${rule.id}`}><X size={16}/></button></div>)}</div> : <div className="empty-state"><ShieldCheck/><strong>No validation rules yet</strong></div>}</section></div><div className="sticky-action"><div><strong>{workflow.validation_rules.length} configured rules</strong><span>{workflow.validation_rules.length < 3 ? `${3-workflow.validation_rules.length} more required` : "Ready for bounded preview"}</span></div><button className="primary-button" disabled={workflow.validation_rules.length < 3} onClick={onPreview}><Save size={17}/>Save workflow & preview</button></div></>;
}

function PreviewScreen({ preview, workflow, onExecute }: { preview: PreviewResult; workflow: Workflow; onExecute: () => void }) {
  return <><ScreenHead eyebrow="PREVIEW BEFORE EXECUTION" title="Review row impact and exceptions." description="This bounded sample uses the same deterministic pipeline as the full run." step="7 of 9"/><section className="metrics-grid"><MetricCard icon={Database} label="Rows read" value={preview.rows_read} note="Bounded preview sample"/><MetricCard icon={CheckCircle2} label="Would write" value={preview.rows_written} note="Passed error gates" tone="success"/><MetricCard icon={XCircle} label="Would reject" value={preview.rows_rejected} note="Never silently discarded" tone="danger"/><MetricCard icon={WandSparkles} label="Rules applied" value={workflow.operations.length + workflow.validation_rules.length} note="Versioned configuration"/></section><div className="tabbed-results"><section className="panel"><div className="panel-title"><div><span className="eyebrow">PROCESSED SAMPLE</span><h3>After cleaning</h3></div><StatusChip value="preview"/></div><DataTable rows={preview.rows} empty="No rows passed the configured validation gates."/></section><section className="panel"><div className="panel-title"><div><span className="eyebrow">VALIDATION FINDINGS</span><h3>{preview.findings.length} explanations</h3></div><AlertTriangle/></div><DataTable rows={preview.findings as unknown as Record<string, unknown>[]} empty="No validation findings in this sample."/></section></div><section className="panel impact-panel"><div className="panel-title"><div><span className="eyebrow">OPERATION IMPACT</span><h3>Before / after evidence</h3></div><Activity/></div>{preview.operation_metrics.map((metric) => <div className="impact-row" key={metric.node_id}><code>{metric.operation_id}</code><span>{metric.rows_in} rows in</span><ArrowRight size={15}/><span>{metric.rows_out} rows out</span><strong>{metric.affected_rows} affected</strong></div>)}</section><div className="sticky-action"><div><strong>Workflow saved and machine-valid</strong><span>Full execution creates a new isolated run directory</span></div><button className="primary-button" onClick={onExecute}><Play size={17}/>Execute full run</button></div></>;
}

function ResultsScreen({ run, onHistory }: { run: RunRecord; onHistory: () => void }) {
  return <><ScreenHead eyebrow="AUDITED RESULT" title={run.status === "succeeded" ? "Run completed safely." : "Run completed with exceptions."} description="The source fingerprint was verified after processing and outputs were reopened before finalisation." step="8 of 9"/><section className={run.status === "succeeded" ? "result-hero success-result" : "result-hero warning-result"}><div>{run.status === "succeeded" ? <CheckCircle2/> : <AlertTriangle/>}</div><span className="eyebrow">RUN STATUS</span><h2>{run.status.replaceAll("_"," ")}</h2><p>Run <code>{run.id}</code> · workflow v{run.workflow_version} · {run.duration_ms} ms</p></section><section className="metrics-grid"><MetricCard icon={Database} label="Rows read" value={run.rows_read} note="Source table records"/><MetricCard icon={CheckCircle2} label="Rows written" value={run.rows_written} note="Processed Data sheet" tone="success"/><MetricCard icon={XCircle} label="Rows rejected" value={run.rows_rejected} note="Reasons included" tone="danger"/><MetricCard icon={Fingerprint} label="Fingerprint" value={run.source_fingerprint.slice(0,8)} note="Unchanged after run"/></section><div className="workspace-grid"><section className="panel"><div className="panel-title"><div><span className="eyebrow">OUTPUT ARTIFACT</span><h3>Professional workbook pack</h3></div><FileOutput/></div><div className="artifact-card"><div className="file-icon large"><FileOutput/></div><div><strong>{run.source_filename.replace(/\.[^.]+$/, "")}_output.xlsx</strong><span>Processed · Summary · Errors · Audit · Metadata · Rules</span></div><a className="primary-button" href={api.artifactUrl(run.id)}><Download size={17}/>Download workbook</a></div></section><section className="panel"><div className="panel-title"><div><span className="eyebrow">SOURCE EVIDENCE</span><h3>Immutable input</h3></div><ShieldCheck/></div><dl className="evidence-list"><div><dt>Source</dt><dd>{run.source_filename}</dd></div><div><dt>SHA-256</dt><dd><code>{run.source_fingerprint}</code></dd></div><div><dt>Reconciliation</dt><dd>{run.rows_read} = {run.rows_written} + {run.rows_rejected} + {run.rows_filtered}</dd></div></dl></section></div><div className="sticky-action"><div><strong>Run evidence is stored locally</strong><span>SQLite contains metadata only, never source rows</span></div><button className="secondary-button" onClick={onHistory}><History size={17}/>View run history</button></div></>;
}

function HistoryScreen({ runs }: { runs: RunRecord[] }) {
  return <><ScreenHead eyebrow="RUN AUDIT" title="Every execution has a history." description="Statuses, fingerprints, counts, duration, and artifact locations remain traceable without storing source rows in the database." step="9 of 9"/><section className="panel"><div className="panel-title"><div><span className="eyebrow">LOCAL RUNS</span><h3>{runs.length} recorded executions</h3></div><History/></div>{runs.length ? <div className="history-table">{runs.map((run) => <article key={run.id}><div className="file-icon"><FileOutput/></div><div><strong>{run.source_filename}</strong><span>{new Date(run.started_at).toLocaleString()} · {run.duration_ms} ms</span></div><span>{run.rows_read} read</span><span>{run.rows_written} written</span><span>{run.rows_rejected} rejected</span><StatusChip value={run.status}/><a className="icon-button" href={api.artifactUrl(run.id)} aria-label={`Download output for ${run.source_filename}`}><Download size={17}/></a></article>)}</div> : <div className="empty-state"><History/><strong>No runs recorded</strong><span>Complete the guided workflow to create the first audit record.</span></div>}</section></>;
}

function buildWorkflow(project: Project, source: SourceHandle, table: TableDiscovery): Workflow {
  const now = new Date().toISOString(); const used = new Map<string,number>();
  const canonical_fields: CanonicalField[] = table.columns.map((column) => { const base=slugify(column.source_name); const count=(used.get(base)??0)+1; used.set(base,count); const id=count===1?base:`${base}_${count}`; return { id, label: column.source_name, data_type: column.inferred_type, required: false, nullable: true, unique: column.is_key_candidate, aliases: [] }; });
  const mappings: ColumnMapping[] = table.columns.map((column,index) => ({ source_column: column.source_name, canonical_field_id: canonical_fields[index].id, confidence: Math.max(.75,table.confidence), user_confirmed: true, constant_value: null, default_value: null }));
  const textField = canonical_fields.find((field) => field.data_type === "text")?.id ?? canonical_fields[0]?.id ?? "field";
  const defaultOps: OperationNode[] = ["text.trim","text.normalise_spaces","text.remove_non_printable"].map((operation_id) => ({ id: crypto.randomUUID(), operation_id, operation_version: 1, config: { field_id: textField }, enabled: true }));
  const requiredField = canonical_fields.find((field) => field.unique)?.id ?? canonical_fields[0]?.id ?? "field";
  const defaultRules: ValidationRule[] = [
    { id: "REQUIRED_1", rule_type: "required", field_id: requiredField, severity: "blocking", reason_code: "REQUIRED_VALUE_MISSING", message: `${requiredField} is required`, config: {} },
    { id: "TYPE_1", rule_type: "data_type", field_id: requiredField, severity: "warning", reason_code: "DATA_TYPE_INVALID", message: `${requiredField} does not match its canonical type`, config: { data_type: canonical_fields.find((field) => field.id===requiredField)?.data_type ?? "text" } },
    { id: "LENGTH_1", rule_type: "text_length", field_id: textField, severity: "warning", reason_code: "TEXT_LENGTH_INVALID", message: `${textField} exceeds the configured length`, config: { min: 0, max: 120 } },
  ];
  return { schema_version:"1.0", compatibility_version:1, id:crypto.randomUUID(), workflow_version:1, project_id:project.id, display_name:`${project.name} · ${source.original_filename}`, source_connector:source.original_filename.toLowerCase().endsWith(".csv")?"file.csv":"file.excel", discovery_overrides:{ sheet_name:table.sheet_name, header_row:table.selected_header_row, header_search_depth:25, preview_rows:25 }, mapping:{ id:crypto.randomUUID(), version:1, canonical_fields, mappings, created_at:now, created_by:"local-user" }, operations:defaultOps, validation_rules:defaultRules, export:{ filename_prefix:"datapilot_output", include_summary:true, include_rejected_rows:true, include_source_metadata:true }, created_at:now, updated_at:now, change_note:"Initial guided workflow" };
}

function messageOf(reason: unknown) { return reason instanceof Error ? reason.message.replace(/^\{"detail":"?|"?\}$/g, "") : "Unexpected local error"; }

export default App;
