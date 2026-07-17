import type { ReactNode } from "react";

interface Props {
  rows: Record<string, unknown>[];
  empty: ReactNode;
  maxRows?: number;
}

export function DataTable({ rows, empty, maxRows = 12 }: Props) {
  if (!rows.length) return <div className="empty-state">{empty}</div>;
  const headers = Object.keys(rows[0]);
  return (
    <div className="table-wrap" tabIndex={0} aria-label="Scrollable data preview">
      <table>
        <thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead>
        <tbody>
          {rows.slice(0, maxRows).map((row, index) => (
            <tr key={String(row.__row_id ?? index)}>
              {headers.map((header) => <td key={header}>{formatCell(row[header])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatCell(value: unknown) {
  if (value === null || value === undefined || value === "") return <span className="null-value">null</span>;
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

