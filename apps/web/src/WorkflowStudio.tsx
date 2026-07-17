import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  AlertTriangle,
  Boxes,
  Braces,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Copy,
  Database,
  Expand,
  Eye,
  FileOutput,
  GitBranch,
  GripVertical,
  Layers3,
  LoaderCircle,
  Maximize2,
  PanelRight,
  Play,
  Plus,
  Redo2,
  Save,
  Search,
  ShieldAlert,
  Undo2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type {
  DagArtifactType,
  DagExecutionPlan,
  DagManualCheckpoint,
  DagRunRecord,
  DagValidationResult,
  DagWorkflow,
  DagWorkflowNode,
  NodeCapability,
  Project,
  SourceHandle,
} from "./types";

type CanvasData = { model: DagWorkflowNode } & Record<string, unknown>;
type CanvasNode = Node<CanvasData, "dagNode">;
type CanvasEdge = Edge<{ sourcePort: string; targetPort: string; contract: string }>;
type Snapshot = { nodes: CanvasNode[]; edges: CanvasEdge[] };

const categoryLabels: Record<string, string> = {
  source: "Sources",
  discovery_mapping: "Discovery & mapping",
  cleaning: "Cleaning",
  validation: "Validation",
  calculation: "Calculation",
  composition: "Composition",
  comparison_reconciliation: "Comparison & reconciliation",
  output: "Outputs",
  control: "Control flow",
  subflow: "Reusable subflows",
};

const templateNames = [
  "Generic File Cleaning and Validation",
  "Monthly Multi-file Consolidation",
  "Old vs New Dataset Comparison",
  "Staged Reconciliation with Manual Review",
  "Data Quality Gate and Evidence Export",
] as const;

const categoryIcons: Record<string, typeof Database> = {
  source: Database,
  discovery_mapping: Eye,
  cleaning: GripVertical,
  validation: ShieldAlert,
  calculation: Braces,
  composition: Layers3,
  comparison_reconciliation: GitBranch,
  output: FileOutput,
  control: GitBranch,
  subflow: Boxes,
};

function colorForArtifact(type: DagArtifactType) {
  if (type === "canonical_dataset" || type === "dataset_collection") return "#23c8ba";
  if (type === "control") return "#f59f43";
  if (type === "comparison_result" || type === "reconciliation_result") return "#a98bff";
  if (type === "evidence_package" || type === "manifest") return "#4fa8ff";
  return "#8095a5";
}

function DagNodeCard({ data, selected }: NodeProps<CanvasNode>) {
  const model = data.model;
  const Icon = categoryIcons[model.category] ?? Boxes;
  return (
    <article className={`dag-node ${selected ? "selected" : ""}`} aria-label={`${model.display_name} node`}>
      <header><span><Icon size={14} /></span><div><strong>{model.display_name}</strong><small>{model.node_type_id} · v{model.node_version}</small></div></header>
      <div className="dag-ports">
        <div>{model.input_ports.map((port, index) => <div className="dag-port input" key={port.id}>
          <Handle id={port.id} type="target" position={Position.Left} style={{ top: 51 + index * 24, background: colorForArtifact(port.artifact_type) }} />
          <span title={port.artifact_type}>{port.display_name}{port.required ? " *" : ""}</span>
        </div>)}</div>
        <div>{model.output_ports.map((port, index) => <div className="dag-port output" key={port.id}>
          <span title={port.artifact_type}>{port.display_name}</span>
          <Handle id={port.id} type="source" position={Position.Right} style={{ top: 51 + index * 24, background: colorForArtifact(port.artifact_type) }} />
        </div>)}</div>
      </div>
      <footer><span>{categoryLabels[model.category]}</span><span className={`risk ${model.resource_estimate.risk}`}>{model.resource_estimate.risk}</span></footer>
    </article>
  );
}

const nodeTypes = { dagNode: DagNodeCard };

function defaultConfiguration(capability: NodeCapability, source?: SourceHandle): Record<string, unknown> {
  if (["source.excel", "source.csv"].includes(capability.type_id)) return { source_id: source?.id ?? crypto.randomUUID() };
  if (capability.type_id === "source.saved_dataset") return { source_id: source?.id ?? crypto.randomUUID(), overrides: {} };
  if (["discovery.inspect", "discovery.table_select"].includes(capability.type_id)) return { overrides: {} };
  if (capability.type_id === "cleaning.operation") return { operation_id: "text.trim", operation_version: 1, config: { field_id: "record_id" }, enabled: true };
  if (capability.type_id === "validation.rules") return { rules: [] };
  if (capability.type_id === "control.manual_approval") return { checkpoint_type: "output_publication_approval", reason: "Review evidence before continuing." };
  if (capability.type_id === "control.merge") return { strategy: "first_available" };
  if (capability.type_id === "control.condition") return { kind: "literal", value: true, value_type: "boolean", field_id: null, function: null, args: [] };
  if (capability.type_id === "control.parameter") return { id: "runtime_value", label: "Runtime value", description: "", data_type: "text", required: false, default_value: "", allowed_values: [], validation: {}, secret: false, override_policy: "allow" };
  if (capability.type_id === "control.stop") return { reason: "Workflow stopped by configured policy." };
  if (capability.type_id === "control.fail") return { reason_code: "DAG_CONFIGURED_FAILURE", message: "Configured failure." };
  if (capability.type_id === "output.json_manifest") return { filename_prefix: "datapilot_manifest" };
  if (capability.type_id === "output.zip_evidence") return { filename_prefix: "datapilot_evidence", include_manifest: true };
  if (["output.excel", "output.csv"].includes(capability.type_id)) return { filename_prefix: "datapilot_output", include_summary: true, include_rejected_rows: true, include_source_metadata: true };
  return {};
}

function makeNode(capability: NodeCapability, position: { x: number; y: number }, source?: SourceHandle): CanvasNode {
  const now = new Date().toISOString();
  const id = `${capability.type_id.replaceAll(".", "_")}_${crypto.randomUUID().slice(0, 8)}`;
  const model: DagWorkflowNode = {
    id,
    node_type_id: capability.type_id,
    node_version: capability.version,
    display_name: capability.display_name,
    category: capability.category,
    position,
    configuration: defaultConfiguration(capability, source),
    input_ports: capability.input_ports,
    output_ports: capability.output_ports,
    retry_classification: capability.retry_classification,
    checkpoint_policy: capability.checkpoint_supported ? "after_success" : "none",
    resource_estimate: { estimated_rows: null, estimated_memory_bytes: null, estimated_candidate_pairs: null, warning_seconds: null, risk: "unknown" },
    entitlement_capability_id: capability.entitlement_capability_id,
    created_at: now,
    updated_at: now,
  };
  return { id, type: "dagNode", position, data: { model } };
}

function compatible(source: DagArtifactType, target: DagArtifactType) {
  return source === target || source === "any" || target === "any";
}

function WorkflowStudioInner({ project, source }: { project: Project; source: SourceHandle | null }) {
  const [capabilities, setCapabilities] = useState<NodeCapability[]>([]);
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<CanvasEdge>([]);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [configText, setConfigText] = useState("{}");
  const [validation, setValidation] = useState<DagValidationResult | null>(null);
  const [plan, setPlan] = useState<DagExecutionPlan | null>(null);
  const [run, setRun] = useState<DagRunRecord | null>(null);
  const [runs, setRuns] = useState<DagRunRecord[]>([]);
  const [versions, setVersions] = useState<DagWorkflow[]>([]);
  const [checkpoints, setCheckpoints] = useState<DagManualCheckpoint[]>([]);
  const [workflowName, setWorkflowName] = useState("Untitled governed workflow");
  const [workflowId] = useState(crypto.randomUUID());
  const [version, setVersion] = useState(1);
  const [lifecycle, setLifecycle] = useState<"draft" | "published">("draft");
  const [needsNewVersion, setNeedsNewVersion] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [rightTab, setRightTab] = useState<"configure" | "problems" | "plan" | "history">("configure");
  const [fullscreen, setFullscreen] = useState(false);
  const [instance, setInstance] = useState<ReactFlowInstance<CanvasNode, CanvasEdge> | null>(null);
  const [dirty, setDirty] = useState(false);
  const undoStack = useRef<Snapshot[]>([]);
  const redoStack = useRef<Snapshot[]>([]);
  const clipboard = useRef<CanvasNode[]>([]);
  const storageKey = `datapilot:dag:${project.id}`;

  const workflow = useMemo<DagWorkflow>(() => {
    const outgoing = new Set(edges.map((edge) => edge.source));
    const outputs = nodes.filter((node) => !outgoing.has(node.id)).flatMap((node) => {
      const port = node.data.model.output_ports[0];
      return port ? [{ id: `${node.id}_${port.id}`, display_name: `${node.data.model.display_name} output`, node_id: node.id, port_id: port.id, artifact_type: port.artifact_type, required: true }] : [];
    });
    const now = new Date().toISOString();
    return {
      schema_version: "3a.1", compatibility_version: 3, id: workflowId, version, project_id: project.id,
      display_name: workflowName, description: "Built in the DataPilot typed visual workflow studio.", lifecycle,
      owner_reference: "local-user", tags: ["visual-workflow"], input_parameters: [],
      nodes: nodes.map((node) => ({ ...node.data.model, position: node.position, updated_at: now })),
      edges: edges.map((edge) => ({ id: edge.id, source_node_id: edge.source, source_port_id: edge.sourceHandle ?? "output", target_node_id: edge.target, target_port_id: edge.targetHandle ?? "input", condition: null, data_contract_reference: edge.data?.contract ?? "typed-artifact/v1" })),
      outputs, multiple_start_policy: "allow",
      retry_policy: { maximum_attempts: 1, retry_deterministic_failures: true, retry_delay_seconds: 0 },
      cancellation_policy: { cooperative: true, preserve_completed_checkpoints: true, publish_partial_outputs: false },
      resource_policy: { maximum_nodes: 250, maximum_edges: 1000, maximum_subflow_depth: 5, maximum_concurrent_ready_nodes: 4, maximum_payload_bytes: 2000000, maximum_parameter_bytes: 100000, maximum_run_history: 1000, checkpoint_retention_days: 30 },
      audit_policy: { record_parameters: true, exclude_sensitive_parameters: true, record_branch_decisions: true, record_node_metrics: true, record_artifact_fingerprints: true },
      change_note: "Visual DAG draft", created_at: now, updated_at: now,
    };
  }, [edges, lifecycle, nodes, project.id, version, workflowId, workflowName]);

  useEffect(() => {
    void Promise.all([api.listDagCapabilities(), api.listDagRuns(project.id)]).then(([items, history]) => {
      setCapabilities(items); setRuns(history);
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        try { const snapshot = JSON.parse(saved) as Snapshot; setNodes(snapshot.nodes); setEdges(snapshot.edges); } catch { localStorage.removeItem(storageKey); }
      }
    }).catch((reason: unknown) => setNotice(reason instanceof Error ? reason.message : "Unable to load workflow capabilities."));
  }, [project.id, setEdges, setNodes, storageKey]);

  useEffect(() => {
    if (!dirty) return;
    const timer = window.setTimeout(() => localStorage.setItem(storageKey, JSON.stringify({ nodes, edges })), 800);
    return () => window.clearTimeout(timer);
  }, [dirty, edges, nodes, storageKey]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => {
    if (!run || ["succeeded", "failed", "cancelled", "waiting_for_review", "recovery_required"].includes(run.status)) return;
    const timer = window.setInterval(() => void api.getDagRun(run.id).then(setRun), 750);
    return () => window.clearInterval(timer);
  }, [run]);

  useEffect(() => {
    if (!run || run.status !== "waiting_for_review") { setCheckpoints([]); return; }
    void api.listDagCheckpoints(run.id).then(setCheckpoints).catch((reason: unknown) => setNotice(message(reason)));
  }, [run]);

  useEffect(() => {
    const selected = nodes.find((node) => node.id === selectedId);
    setConfigText(JSON.stringify(selected?.data.model.configuration ?? {}, null, 2));
  }, [nodes, selectedId]);

  const checkpoint = useCallback(() => {
    undoStack.current.push({ nodes: structuredClone(nodes), edges: structuredClone(edges) });
    if (undoStack.current.length > 50) undoStack.current.shift();
    redoStack.current = [];
    if (lifecycle === "published") {
      setVersion((current) => current + 1); setLifecycle("draft"); setNeedsNewVersion(true);
    }
    setDirty(true);
  }, [edges, lifecycle, nodes]);

  const addCapability = useCallback((capability: NodeCapability, position?: { x: number; y: number }) => {
    checkpoint();
    setNodes((current) => [...current, makeNode(capability, position ?? { x: 120 + current.length * 32, y: 100 + current.length * 28 }, source ?? undefined)]);
  }, [checkpoint, setNodes, source]);

  const onConnect = useCallback((connection: Connection) => {
    const sourceNode = nodes.find((node) => node.id === connection.source)?.data.model;
    const targetNode = nodes.find((node) => node.id === connection.target)?.data.model;
    const sourcePort = sourceNode?.output_ports.find((port) => port.id === connection.sourceHandle);
    const targetPort = targetNode?.input_ports.find((port) => port.id === connection.targetHandle);
    if (!sourcePort || !targetPort || !compatible(sourcePort.artifact_type, targetPort.artifact_type)) {
      setNotice(`Incompatible connection: ${sourcePort?.artifact_type ?? "unknown"} → ${targetPort?.artifact_type ?? "unknown"}`); return;
    }
    checkpoint();
    setEdges((current) => addEdge({ ...connection, id: `edge_${crypto.randomUUID().slice(0, 10)}`, type: "smoothstep", animated: false, markerEnd: { type: MarkerType.ArrowClosed }, data: { sourcePort: sourcePort.id, targetPort: targetPort.id, contract: `${sourcePort.artifact_type}/v1` } }, current));
  }, [checkpoint, nodes, setEdges]);

  function undo() { const prior = undoStack.current.pop(); if (!prior) return; redoStack.current.push({ nodes, edges }); setNodes(prior.nodes); setEdges(prior.edges); setDirty(true); }
  function redo() { const next = redoStack.current.pop(); if (!next) return; undoStack.current.push({ nodes, edges }); setNodes(next.nodes); setEdges(next.edges); setDirty(true); }
  function alignLeft() { checkpoint(); const selected = nodes.filter((node) => node.selected); const x = Math.min(...selected.map((node) => node.position.x)); if (Number.isFinite(x)) setNodes((items) => items.map((node) => node.selected ? { ...node, position: { ...node.position, x } } : node)); }
  function copySelected() { clipboard.current = structuredClone(nodes.filter((node) => node.selected)); setNotice(`${clipboard.current.length} node(s) copied.`); }
  function pasteSelected() { if (!clipboard.current.length) return; checkpoint(); setNodes((items) => [...items, ...clipboard.current.map((node) => { const id = `${node.data.model.node_type_id.replaceAll(".", "_")}_${crypto.randomUUID().slice(0, 8)}`; return { ...node, id, selected: false, position: { x: node.position.x + 36, y: node.position.y + 36 }, data: { model: { ...node.data.model, id, display_name: `${node.data.model.display_name} copy` } } }; })]); }

  async function validate() { setBusy("Validating typed graph…"); try { const result = await api.validateDag(workflow); setValidation(result); setRightTab("problems"); setNotice(result.valid ? "Static validation passed." : `${result.findings.length} problem(s) require attention.`); } catch (reason) { setNotice(message(reason)); } finally { setBusy(null); } }
  async function previewPlan() { setBusy("Compiling execution plan…"); try { setPlan(await api.planDag(workflow)); setRightTab("plan"); } catch (reason) { setNotice(message(reason)); } finally { setBusy(null); } }
  async function refreshVersions(id = workflow.id) { setVersions(await api.listDagWorkflowHistory(id)); }
  async function save() { setBusy("Saving immutable draft metadata…"); try { const saved = needsNewVersion ? await api.createDagVersion(workflow.id, { ...workflow, lifecycle: "draft" }, "Visual workflow update") : await api.saveDag({ ...workflow, lifecycle: "draft" }); setVersion(saved.version); setNeedsNewVersion(false); setLifecycle("draft"); setDirty(false); localStorage.setItem(storageKey, JSON.stringify({ nodes, edges })); await refreshVersions(saved.id); setNotice(`Draft saved locally as version ${saved.version}.`); } catch (reason) { setNotice(message(reason)); } finally { setBusy(null); } }
  async function publish() { setBusy("Validating and publishing…"); try { let candidate = workflow; if (needsNewVersion) { candidate = await api.createDagVersion(workflow.id, { ...workflow, lifecycle: "draft" }, "Visual workflow update"); setVersion(candidate.version); setNeedsNewVersion(false); } else { candidate = await api.saveDag({ ...workflow, lifecycle: "draft" }); } const published = await api.publishDag(candidate.id, candidate.version); setVersion(published.version); setLifecycle(published.lifecycle === "published" ? "published" : "draft"); setDirty(false); await refreshVersions(published.id); setNotice(`Version ${published.version} published. Future edits create a new version.`); } catch (reason) { setNotice(message(reason)); } finally { setBusy(null); } }
  async function execute() { setBusy("Queueing background execution…"); try { const queued = await api.submitDag(workflow); setRun(queued); setRightTab("history"); } catch (reason) { setNotice(message(reason)); } finally { setBusy(null); } }

  async function compareLatestVersions() { if (versions.length < 2) { setNotice("Save at least two versions before comparing."); return; } const ordered = [...versions].sort((a, b) => b.version - a.version); const diff = await api.diffDagWorkflows(ordered[1], ordered[0]); setNotice(`v${diff.from_version} → v${diff.to_version}: ${diff.items.length} governed change(s), ${diff.compatible ? "compatible" : "review required"}.`); }
  async function cloneWorkflow() { const clone = await api.cloneDagWorkflow(workflow.id, `${workflowName} copy`); setNotice(`Clone ${clone.display_name} created as draft v${clone.version}.`); }
  async function restoreVersion(sourceVersion: number) { const restored = await api.restoreDagWorkflow(workflow.id, sourceVersion); setNodes(restored.nodes.map((model) => ({ id: model.id, type: "dagNode", position: model.position, data: { model } }))); setEdges(restored.edges.map((edge) => ({ id: edge.id, source: edge.source_node_id, sourceHandle: edge.source_port_id, target: edge.target_node_id, targetHandle: edge.target_port_id, type: "smoothstep", markerEnd: { type: MarkerType.ArrowClosed }, data: { sourcePort: edge.source_port_id, targetPort: edge.target_port_id, contract: edge.data_contract_reference ?? "typed-artifact/v1" } }))); setWorkflowName(restored.display_name); setVersion(restored.version); setLifecycle("draft"); setNeedsNewVersion(false); setDirty(false); await refreshVersions(); setNotice(`Version ${sourceVersion} restored as new draft v${restored.version}.`); }
  async function decideCheckpoint(checkpoint: DagManualCheckpoint, action: "approve" | "reject") { await api.decideDagCheckpoint(checkpoint.id, action); setCheckpoints(await api.listDagCheckpoints(checkpoint.run_id)); if (action === "approve") setRun(await api.resumeDagRun(checkpoint.run_id)); else setRun(await api.getDagRun(checkpoint.run_id)); }

  function applyConfiguration() {
    if (!selectedId) return;
    try {
      const parsed = JSON.parse(configText) as Record<string, unknown>; checkpoint();
      setNodes((items) => items.map((node) => node.id === selectedId ? { ...node, data: { model: { ...node.data.model, configuration: parsed, updated_at: new Date().toISOString() } } } : node));
      setNotice("Node configuration updated. Revalidate before publishing.");
    } catch { setNotice("Configuration must be valid JSON."); }
  }

  function loadTemplate(name: typeof templateNames[number]) {
    const definitions: Record<typeof name, { types: string[]; links: Array<[number, string, number, string]> }> = {
      "Generic File Cleaning and Validation": { types: ["source.saved_dataset", "cleaning.operation", "validation.rules", "output.excel"], links: [[0, "dataset", 1, "dataset"], [1, "dataset", 2, "dataset"], [2, "dataset", 3, "input"]] },
      "Monthly Multi-file Consolidation": { types: ["source.saved_dataset", "source.saved_dataset", "composition.append", "output.csv"], links: [[0, "dataset", 2, "datasets"], [1, "dataset", 2, "datasets"], [2, "dataset", 3, "input"]] },
      "Old vs New Dataset Comparison": { types: ["source.saved_dataset", "source.saved_dataset", "comparison.dataset", "output.json_manifest"], links: [[0, "dataset", 2, "left"], [1, "dataset", 2, "right"], [2, "comparison", 3, "input"]] },
      "Staged Reconciliation with Manual Review": { types: ["source.saved_dataset", "source.saved_dataset", "reconciliation.staged", "reconciliation.manual_review", "output.zip_evidence"], links: [[0, "dataset", 2, "left"], [1, "dataset", 2, "right"], [2, "result", 3, "result"], [3, "result", 4, "input"], [3, "decisions", 4, "input"]] },
      "Data Quality Gate and Evidence Export": { types: ["source.saved_dataset", "validation.rules", "control.manual_approval", "output.excel"], links: [[0, "dataset", 1, "dataset"], [1, "dataset", 2, "input"], [2, "approved", 3, "input"]] },
    };
    const definition = definitions[name];
    const selectedCapabilities = definition.types.map((typeId) => capabilities.find((item) => item.type_id === typeId));
    if (selectedCapabilities.some((item) => !item)) { setNotice("One or more template node capabilities are unavailable."); return; }
    checkpoint();
    const templateNodes = selectedCapabilities.map((capability, index) => makeNode(capability!, { x: 100 + index * 310, y: index === 1 && definition.types[0] === definition.types[1] ? 330 : 150 }, source ?? undefined));
    templateNodes.forEach((node) => {
      if (node.data.model.node_type_id === "comparison.dataset") node.data.model.configuration = { schema_version: "2b.1", id: crypto.randomUUID(), version: 1, project_id: project.id, left_dataset_id: crypto.randomUUID(), right_dataset_id: crypto.randomUUID(), business_key_fields: ["record_key"], compare_fields: ["amount"] };
      if (node.data.model.node_type_id === "reconciliation.staged") node.data.model.configuration = { schema_version: "2b.1", id: crypto.randomUUID(), version: 1, project_id: project.id, display_name: "Staged reconciliation", left_dataset_id: crypto.randomUUID(), right_dataset_id: crypto.randomUUID(), evidence_fields: ["record_key", "amount"], stages: [{ schema_version: "2b.1", id: "exact_key", name: "Exact key", priority: 1, left_key_fields: ["record_key"], right_key_fields: ["record_key"], method: "exact" }] };
      if (node.data.model.node_type_id === "reconciliation.manual_review") node.data.model.configuration = { checkpoint_type: "reconciliation_review", reason: "Review ambiguous candidates before evidence publication." };
    });
    setNodes(templateNodes);
    setEdges(definition.links.map(([sourceIndex, sourcePort, targetIndex, targetPort]) => ({ id: `edge_${crypto.randomUUID().slice(0, 8)}`, source: templateNodes[sourceIndex].id, sourceHandle: sourcePort, target: templateNodes[targetIndex].id, targetHandle: targetPort, type: "smoothstep", markerEnd: { type: MarkerType.ArrowClosed }, data: { sourcePort, targetPort, contract: `${templateNodes[sourceIndex].data.model.output_ports.find((port) => port.id === sourcePort)?.artifact_type ?? "any"}/v1` } })));
    setWorkflowName(name); setLifecycle("draft"); setNotice(`${name} template loaded as an editable draft.`);
  }

  const selected = nodes.find((node) => node.id === selectedId)?.data.model;
  const filtered = capabilities.filter((item) => `${item.display_name} ${item.type_id} ${categoryLabels[item.category]}`.toLowerCase().includes(search.toLowerCase()));
  const grouped = Object.entries(filtered.reduce<Record<string, NodeCapability[]>>((groups, item) => {
    (groups[item.category] ??= []).push(item); return groups;
  }, {}));

  return <section className={`workflow-studio ${fullscreen ? "fullscreen" : ""}`} aria-label="Visual workflow studio">
    <header className="dag-toolbar">
      <div className="dag-title"><span>Visual DAG</span><input aria-label="Workflow name" value={workflowName} onChange={(event) => { if (lifecycle === "published") { setVersion((current) => current + 1); setLifecycle("draft"); setNeedsNewVersion(true); } setWorkflowName(event.target.value); setDirty(true); }} /><small>v{version} · <b className={lifecycle}>{lifecycle}</b>{dirty ? " · unsaved" : ""}</small></div>
      <div className="dag-tool-group"><button onClick={undo} title="Undo"><Undo2 size={15} /></button><button onClick={redo} title="Redo"><Redo2 size={15} /></button><button onClick={copySelected} title="Copy selected"><Copy size={15} /></button><button onClick={pasteSelected} title="Paste"><Plus size={15} /></button><button onClick={alignLeft} title="Align selected left"><GripVertical size={15} /></button></div>
      <div className="dag-tool-group"><button onClick={() => instance?.fitView({ padding: .2 })} title="Fit view"><Expand size={15} /></button><button onClick={() => setFullscreen(!fullscreen)} title="Toggle fullscreen"><Maximize2 size={15} /></button><button onClick={() => setRightTab("configure")} title="Toggle details"><PanelRight size={15} /></button></div>
      <div className="dag-actions"><button className="secondary-button" onClick={() => void validate()}><CheckCircle2 size={14} /> Validate</button><button className="secondary-button" onClick={() => void previewPlan()}><Eye size={14} /> Plan</button><button className="secondary-button" onClick={() => void save()}><Save size={14} /> Save</button><button className="secondary-button" onClick={() => void publish()}>Publish</button><button className="primary-button" disabled={lifecycle !== "published"} onClick={() => void execute()}><Play size={14} /> Run</button></div>
    </header>
    {(notice || busy) && <div className="dag-notice">{busy && <LoaderCircle className="spin" size={15} />}<span>{busy ?? notice}</span>{notice && !busy && <button onClick={() => setNotice(null)} aria-label="Dismiss"><X size={14} /></button>}</div>}
    <div className="dag-layout">
      <aside className="dag-palette" aria-label="Node palette">
        <label><Search size={14} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search nodes" aria-label="Search node palette" /></label>
        <details><summary><Boxes size={14} /> Templates <ChevronDown size={13} /></summary><div className="template-list">{templateNames.map((name) => <button key={name} onClick={() => loadTemplate(name)}>{name}</button>)}</div></details>
        <div className="palette-scroll">{grouped.map(([category, items]) => <details open key={category}><summary>{categoryLabels[category]} <span>{items?.length}</span></summary>{items?.map((capability) => { const Icon = categoryIcons[capability.category] ?? Boxes; return <button className="palette-node" key={`${capability.type_id}:${capability.version}`} draggable onDragStart={(event) => event.dataTransfer.setData("application/datapilot-node", capability.type_id)} onClick={() => addCapability(capability)}><Icon size={14} /><span>{capability.display_name}<small>{capability.type_id}</small></span><Plus size={13} /></button>; })}</details>)}</div>
      </aside>
      <main className="dag-canvas" onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "move"; }} onDrop={(event) => { event.preventDefault(); const typeId = event.dataTransfer.getData("application/datapilot-node"); const capability = capabilities.find((item) => item.type_id === typeId); if (capability && instance) addCapability(capability, instance.screenToFlowPosition({ x: event.clientX, y: event.clientY })); }}>
        {nodes.length === 0 && <div className="dag-empty"><Boxes size={28} /><strong>Build a governed workflow</strong><span>Drag a typed node here, choose a template, or use the keyboard-accessible add buttons.</span></div>}
        <ReactFlow<CanvasNode, CanvasEdge> nodes={nodes} edges={edges} nodeTypes={nodeTypes} onInit={setInstance} onNodesChange={(changes) => { const material = changes.some((change) => change.type === "remove" || (change.type === "position" && change.dragging === false)); if (material) checkpoint(); onNodesChange(changes); if (material) setDirty(true); }} onEdgesChange={(changes) => { if (changes.some((change) => change.type === "remove")) checkpoint(); onEdgesChange(changes); if (changes.some((change) => change.type === "remove")) setDirty(true); }} onConnect={onConnect} onNodeClick={(_, node) => { setSelectedId(node.id); setRightTab("configure"); }} onPaneClick={() => setSelectedId(null)} fitView snapToGrid snapGrid={[16, 16]} minZoom={.2} maxZoom={2} deleteKeyCode={["Backspace", "Delete"]} multiSelectionKeyCode={["Control", "Meta"]} selectionOnDrag>
          <Background gap={16} size={1} color="#27475d" /><MiniMap pannable zoomable nodeColor="#1c5367" maskColor="rgba(5,19,29,.72)" /><Controls showInteractive={false} />
        </ReactFlow>
      </main>
      <aside className="dag-inspector" aria-label="Workflow details">
        <nav>{(["configure", "problems", "plan", "history"] as const).map((tab) => <button key={tab} className={rightTab === tab ? "active" : ""} onClick={() => setRightTab(tab)}>{tab === "configure" ? "Configure" : tab === "problems" ? `Problems${validation?.findings.length ? ` (${validation.findings.length})` : ""}` : tab === "plan" ? "Plan" : "Runs"}</button>)}</nav>
        {rightTab === "configure" && <div className="inspector-body">{selected ? <><div className="inspector-heading"><span className="node-category">{categoryLabels[selected.category]}</span><h3>{selected.display_name}</h3><code>{selected.node_type_id}@{selected.node_version}</code></div><label>Display name<input value={selected.display_name} onChange={(event) => { if (lifecycle === "published") checkpoint(); setNodes((items) => items.map((node) => node.id === selected.id ? { ...node, data: { model: { ...node.data.model, display_name: event.target.value } } } : node)); setDirty(true); }} /></label><label>Typed configuration<textarea rows={14} value={configText} onChange={(event) => setConfigText(event.target.value)} spellCheck={false} /></label><button className="primary-button full" onClick={applyConfiguration}>Apply configuration</button><button className="variable-button" onClick={() => setConfigText((value) => value.replace(/}\s*$/, ',\n  "value": "${parameters.runtime_value}"\n}'))}><Braces size={13} /> Insert parameter reference</button><div className="port-contracts"><h4>Port contracts</h4>{[...selected.input_ports, ...selected.output_ports].map((port) => <div key={`${port.id}:${port.artifact_type}`}><span>{port.display_name}</span><code>{port.artifact_type}</code></div>)}</div></> : <div className="inspector-empty"><PanelRight size={25} /><strong>Select a node</strong><span>Configuration, typed ports, resource estimates and version details appear here.</span></div>}</div>}
        {rightTab === "problems" && <div className="inspector-body"><div className="inspector-heading"><span className="node-category">Static validation</span><h3>{validation ? (validation.valid ? "Ready to plan" : "Action required") : "Not validated"}</h3></div>{validation?.findings.map((finding, index) => <button className={`problem-item ${finding.severity}`} key={`${finding.reason_code}:${index}`} onClick={() => finding.node_id && setSelectedId(finding.node_id)}><AlertTriangle size={15} /><span><strong>{finding.reason_code}</strong>{finding.explanation}<small>{finding.suggested_resolution}</small></span><ChevronRight size={14} /></button>)}{validation?.valid && <div className="success-state"><CheckCircle2 size={24} /><strong>All static checks passed</strong><span>{validation.topological_order.length} nodes have a valid topological order.</span></div>}</div>}
        {rightTab === "plan" && <div className="inspector-body">{plan ? <><div className="plan-metrics"><article><strong>{plan.nodes.length}</strong><span>nodes</span></article><article><strong>{Math.max(0, ...plan.nodes.map((node) => node.parallel_group))}</strong><span>parallel groups</span></article><article><strong>{plan.manual_checkpoint_nodes.length}</strong><span>manual gates</span></article></div><code className="fingerprint">{plan.plan_fingerprint}</code><div className="outline-list">{plan.nodes.map((node) => <button key={node.node_id} onClick={() => setSelectedId(node.node_id)}><span>{node.sequence}</span><strong>{nodes.find((item) => item.id === node.node_id)?.data.model.display_name}</strong><small>Group {node.parallel_group}</small></button>)}</div>{plan.resource_warnings.map((warning) => <div className="resource-warning" key={warning}><AlertTriangle size={14} />{warning}</div>)}</> : <div className="inspector-empty"><Eye size={25} /><strong>No plan compiled</strong><span>Validate and preview the plan to inspect order, parallel groups, dead outputs and manual gates.</span></div>}</div>}
        {rightTab === "history" && <div className="inspector-body">{run && <div className={`live-run ${run.status}`}><div><Clock3 size={17} /><strong>{run.status.replaceAll("_", " ")}</strong><span>{Math.round(run.progress_percent)}%</span></div><div className="run-progress"><span style={{ width: `${run.progress_percent}%` }} /></div><small>{run.current_node_id ? `Current: ${run.current_node_id}` : run.error_message ?? "Background execution queued"}</small>{!["succeeded", "failed", "cancelled"].includes(run.status) && <button onClick={() => void api.cancelDagRun(run.id).then(setRun)}>Cancel run</button>}{["failed", "recovery_required"].includes(run.status) && <button onClick={() => void api.retryDagRun(run.id).then(setRun)}>Retry deterministic run</button>}</div>}{checkpoints.filter((item) => item.status === "waiting").map((checkpoint) => <article className="checkpoint-review" key={checkpoint.id}><strong>Manual checkpoint</strong><span>{checkpoint.reason}</span><div>{checkpoint.available_actions.includes("approve") && <button onClick={() => void decideCheckpoint(checkpoint, "approve")}>Approve & resume</button>}{checkpoint.available_actions.includes("reject") && <button onClick={() => void decideCheckpoint(checkpoint, "reject")}>Reject</button>}</div></article>)}<div className="version-controls"><h4>Workflow versions</h4><div><button onClick={() => void refreshVersions()}>Refresh history</button><button onClick={() => void compareLatestVersions()}>Compare latest</button><button onClick={() => void cloneWorkflow()}>Clone</button></div>{[...versions].sort((a, b) => b.version - a.version).map((item) => <article key={`${item.id}:${item.version}`}><span>v{item.version} · {item.lifecycle}</span>{item.version !== version && <button onClick={() => void restoreVersion(item.version)}>Restore as new draft</button>}</article>)}</div><div className="run-list">{runs.map((item) => <article key={item.id}><span className={`run-dot ${item.status}`} /><div><strong>{item.status.replaceAll("_", " ")}</strong><small>{new Date(item.created_at).toLocaleString()}</small></div><code>{item.id.slice(0, 8)}</code></article>)}</div></div>}
      </aside>
    </div>
  </section>;
}

function message(reason: unknown) { return reason instanceof Error ? reason.message : "The workflow action could not be completed."; }

export function WorkflowStudio(props: { project: Project; source: SourceHandle | null }) {
  return <ReactFlowProvider><WorkflowStudioInner {...props} /></ReactFlowProvider>;
}
