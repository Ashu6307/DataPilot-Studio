export function StatusChip({ value }: { value: string }) {
  const tone = ["succeeded", "published", "active", "visible"].includes(value) ? "success" : ["failed", "blocking", "error"].includes(value) ? "danger" : ["partial", "warning", "hidden"].includes(value) ? "warning" : "info";
  return <span className={`status-chip ${tone}`}><span aria-hidden="true">●</span>{value.replaceAll("_", " ")}</span>;
}

