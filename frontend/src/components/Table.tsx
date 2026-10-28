import type { ReactNode } from 'react'

export interface Column<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
}

interface TableProps<T> {
  columns: Column<T>[]
  rows: T[]
  getKey: (row: T) => string | number
  emptyText?: string
}

export function Table<T>({ columns, rows, getKey, emptyText = 'Немає даних' }: TableProps<T>) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>{columns.map((c) => <th key={c.key} scope="col">{c.header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr><td className="table__empty" colSpan={columns.length}>{emptyText}</td></tr>
          ) : (
            rows.map((row) => (
              <tr key={getKey(row)}>{columns.map((c) => <td key={c.key}>{c.render(row)}</td>)}</tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
