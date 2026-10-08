import type { ReactNode } from "react";

export type DataTableColumn<T> = { key: string; header: ReactNode; render: (row: T) => ReactNode };

export function DataTable<T extends { id?: string | number }>({ columns, rows, empty }: { columns: DataTableColumn<T>[]; rows: T[]; empty?: ReactNode }) {
  return <div className="data-table"><div className="data-table-header">{columns.map((column) => <span key={column.key}>{column.header}</span>)}</div>{rows.length === 0 ? empty ?? <div className="empty-state">No records</div> : rows.map((row, index) => <div className="data-table-row" key={row.id ?? index}>{columns.map((column) => <span key={column.key}>{column.render(row)}</span>)}</div>)}</div>;
}
