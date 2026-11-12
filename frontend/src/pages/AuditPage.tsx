import { useEffect, useMemo, useState } from 'react'
import { fetchAuditLog } from '../api/governance'
import type { AuditLogEntry } from '../api/types'
import { ErrorMessage } from '../components/ErrorMessage'

const integer = new Intl.NumberFormat('uk-UA')

const RESULT_CLASS: Record<string, string> = {
  SUCCESS: 'badge--published',
  DENY: 'badge--attention',
  FORBIDDEN: 'badge--attention',
  UNAUTHORIZED: 'badge--attention',
  INVALID: 'badge--attention',
  CONFLICT: 'badge--expired',
  NOT_FOUND: 'badge--expired',
}

const formatTimestamp = (iso: string) =>
  new Date(iso).toLocaleString('uk-UA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })

export default function AuditPage() {
  const [rows, setRows] = useState<AuditLogEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [action, setAction] = useState('all')
  const [result, setResult] = useState('all')

  const load = () => {
    setError(null)
    fetchAuditLog()
      .then(setRows)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : 'Не вдалося завантажити журнал аудиту'),
      )
  }

  useEffect(() => {
    load()
  }, [])

  const actions = useMemo(
    () => Array.from(new Set((rows ?? []).map((row) => row.action))).sort(),
    [rows],
  )
  const results = useMemo(
    () => Array.from(new Set((rows ?? []).map((row) => row.result))).sort(),
    [rows],
  )

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (rows ?? []).filter((row) => {
      if (action !== 'all' && row.action !== action) return false
      if (result !== 'all' && row.result !== result) return false
      if (!q) return true
      return [row.actor, row.action, row.object, row.result].some((value) =>
        value.toLowerCase().includes(q),
      )
    })
  }, [rows, query, action, result])

  const stats = useMemo(() => {
    const list = rows ?? []
    return {
      total: list.length,
      denied: list.filter((row) => row.result !== 'SUCCESS').length,
      actors: new Set(list.map((row) => row.actor)).size,
    }
  }, [rows])

  return (
    <>
      <div className="page-header page-header--row">
        <div className="page-header">
          <h1>Журнал аудиту</h1>
          <p className="subtitle">
            Хто, коли, яка дія, над яким об’єктом і з яким результатом. Персональні дані
            в журнал не записуються.
          </p>
        </div>
        <button type="button" className="btn btn--secondary" onClick={load} disabled={!rows}>
          Оновити
        </button>
      </div>

      <div className="stats">
        <div className="stat">
          <span className="stat__label">Записів</span>
          <span className="stat__value">{integer.format(stats.total)}</span>
        </div>
        <div className="stat">
          <span className="stat__label">Відмов і помилок</span>
          <span className="stat__value stat__value--warn">{integer.format(stats.denied)}</span>
        </div>
        <div className="stat">
          <span className="stat__label">Унікальних акторів</span>
          <span className="stat__value">{integer.format(stats.actors)}</span>
        </div>
      </div>

      {error && <ErrorMessage title="Не вдалося завантажити журнал">{error}</ErrorMessage>}

      {!error && rows === null && <p className="subtitle">Завантаження…</p>}

      {rows !== null && (
        <section className="card card--table-section">
          <div className="table-toolbar">
            <div className="table-toolbar__search">
              <input
                type="search"
                className="table-toolbar__input"
                placeholder="Пошук за актором, дією або об’єктом…"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="Пошук у журналі аудиту"
              />
            </div>
            <div className="table-toolbar__filters">
              <label className="filter-select-label">
                <span>Дія:</span>
                <select
                  className="filter-select"
                  value={action}
                  onChange={(event) => setAction(event.target.value)}
                >
                  <option value="all">Усі</option>
                  {actions.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label className="filter-select-label">
                <span>Результат:</span>
                <select
                  className="filter-select"
                  value={result}
                  onChange={(event) => setResult(event.target.value)}
                >
                  <option value="all">Усі</option>
                  {results.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Час</th>
                  <th scope="col">Актор</th>
                  <th scope="col">Дія</th>
                  <th scope="col">Об’єкт</th>
                  <th scope="col">Результат</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td className="table__empty" colSpan={5}>
                      {rows.length === 0
                        ? 'Журнал порожній'
                        : 'За заданими фільтрами записів не знайдено'}
                    </td>
                  </tr>
                ) : (
                  filtered.map((row) => (
                    <tr key={row.id}>
                      <td className="cell-muted">{formatTimestamp(row.timestamp)}</td>
                      <td>{row.actor}</td>
                      <td>
                        <strong>{row.action}</strong>
                      </td>
                      <td>
                        <code className="qr-code">{row.object}</code>
                      </td>
                      <td>
                        <span className={`badge badge--status ${RESULT_CLASS[row.result] ?? 'badge--uploaded'}`}>
                          <span className="badge__dot" aria-hidden="true" />
                          {row.result}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="card__footer">
            <span className="caption">
              Показано {filtered.length} з {rows.length} записів
            </span>
          </div>
        </section>
      )}
    </>
  )
}
