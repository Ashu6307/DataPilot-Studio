import type { LucideIcon } from "lucide-react";

export function MetricCard({ label, value, note, icon: Icon, tone = "neutral" }: { label: string; value: string | number; note: string; icon: LucideIcon; tone?: string }) {
  return (
    <article className={`metric-card ${tone}`}>
      <div className="metric-icon" aria-hidden="true"><Icon size={18} /></div>
      <p>{label}</p>
      <strong>{value}</strong>
      <span>{note}</span>
    </article>
  );
}

