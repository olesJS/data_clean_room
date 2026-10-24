import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchDatasets } from '../api/datasets'
import type { DatasetVersion } from '../api/types'
import { ClassBadge, StatusBadge } from '../components/Badges'
import { ErrorMessage } from '../components/ErrorMessage'
import { QualityScore } from '../components/QualityScore'
import { Table, type Column } from '../components/Table'

const formatDate = (iso: string) => new Date(iso).toLocaleDateString('uk-UA')

export default function DatasetsPage() {
  const [rows, setRows] = useState<DatasetVersion[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchDatasets()
      .then((data) => { if (!cancelled) setRows(data) })
      .catch((err: unknown) => { if (!cancelled) setError(err instanceof Error ? err.message : 'Не вдалося завантажити набори') })
    return () => { cancelled = true }
  }, [])

  const stats = useMemo(() => {
    const list = rows ?? []
    return {
      total: new Set(list.map((r) => r.dataset_id)).size,
      published: list.filter((r) => r.status === 'Published').length,
      attention: list.filter((r) => r.status === 'Needs attention').length,
    }
  }, [rows])

  const columns = useMemo<Column<DatasetVersion>[]>(() => {
    const numberById = new Map((rows ?? []).map((r) => [r.id, r.version_number]))
    return [
      { key: 'id', header: 'ID', render: (r) => <span className="cell-muted">{r.dataset_id}</span> },
      { key: 'name', header: 'Назва набору', render: (r) => <span className="cell-strong">{r.file_name}</span> },
      { key: 'format', header: 'Формат', render: (r) => <span className="cell-muted">{r.format}</span> },
      { key: 'class', header: 'Клас', render: (r) => <ClassBadge value={r.data_class} /> },
      { key: 'status', header: 'Статус версії', render: (r) => <StatusBadge value={r.status} /> },
      { key: 'score', header: 'Quality Score', render: (r) => <QualityScore score={r.quality_score} /> },
      {
        key: 'version',
        header: 'Версія',
        render: (r) => (
          <span className="cell-two">
            <strong>v{r.version_number} · {r.parent_version_id === null ? 'оригінал' : 'очищена'}</strong>
            <small>{r.parent_version_id === null ? '—' : `← v${numberById.get(r.parent_version_id) ?? '?'}`}</small>
          </span>
        ),
      },
      { key: 'updated', header: 'Оновлено', render: (r) => <span className="cell-muted">{formatDate(r.updated_at)}</span> },
    ]
  }, [rows])

  const loaded = rows !== null
  const empty = loaded && rows.length === 0

  return (
    <>
      <div className="page-header page-header--row">
        <div className="page-header">
          <h1>Мої набори даних</h1>
          <p className="subtitle">Усі набори, їх клас, версії та статуси</p>
        </div>
        {!empty && <Link className="btn" to="/upload">Імпортувати дані</Link>}
      </div>

      <div className="stats">
        <div className="stat"><span className="stat__label">Усього наборів</span><span className="stat__value">{stats.total}</span></div>
        <div className="stat"><span className="stat__label">Опубліковано (версії)</span><span className="stat__value stat__value--ok">{stats.published}</span></div>
        <div className="stat"><span className="stat__label">Потребують уваги (версії)</span><span className="stat__value stat__value--warn">{stats.attention}</span></div>
      </div>

      {error && <ErrorMessage title="Не вдалося завантажити список">{error}</ErrorMessage>}
      {!error && !loaded && <p className="subtitle">Завантаження…</p>}
      {empty && (
        <div className="empty">
          <h2>Ще немає наборів даних</h2>
          <p>Імпортуйте перший файл CSV або JSON, щоб побачити його профіль і Quality Score</p>
          <Link className="btn" to="/upload">Імпортувати дані</Link>
        </div>
      )}
      {loaded && !empty && (
        <>
          <Table columns={columns} rows={rows} getKey={(r) => r.id} />
          <p className="caption">Примітки: ≥80 — «Висока якість», 50–79 — «Середня якість», &lt;50 — «Низька якість»</p>
        </>
      )}
    </>
  )
}
