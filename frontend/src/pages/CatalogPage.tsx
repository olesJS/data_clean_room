import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchCatalog } from '../api/governance'
import { createExchangeRequest, fetchExchangeRequests } from '../api/exchange'
import { ApiError } from '../api/client'
import {
  EXCHANGE_STATUS_LABELS,
  LEGAL_BASIS_PURPOSE_LABELS,
  type CatalogItem,
  type ExchangeRequest,
  type LegalBasisPurpose,
} from '../api/types'
import { useAuth } from '../auth/useAuth'
import { ClassBadge } from '../components/Badges'
import { ErrorMessage } from '../components/ErrorMessage'
import { QualityScore } from '../components/QualityScore'

const PURPOSES: LegalBasisPurpose[] = ['analytics', 'research', 'reporting', 'publication']
const integer = new Intl.NumberFormat('uk-UA')

const formatDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString('uk-UA') : '—'

const requestTone = (status: string): string => {
  if (status === 'Approved' || status === 'Downloaded') return 'badge--published'
  if (status === 'Requested') return 'badge--attention'
  return 'badge--expired'
}

export default function CatalogPage() {
  const { role } = useAuth()
  const isConsumer = role === 'DataConsumer'
  const [items, setItems] = useState<CatalogItem[] | null>(null)
  const [requests, setRequests] = useState<ExchangeRequest[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [selected, setSelected] = useState<CatalogItem | null>(null)
  const [purpose, setPurpose] = useState<LegalBasisPurpose>('analytics')
  const [submitting, setSubmitting] = useState(false)

  const load = useCallback(() => {
    setError(null)
    Promise.all([
      fetchCatalog(),
      isConsumer ? fetchExchangeRequests() : Promise.resolve([]),
    ])
      .then(([catalog, ownRequests]) => {
        setItems(catalog)
        setRequests(ownRequests)
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : 'Не вдалося завантажити каталог'),
      )
  }, [isConsumer])

  useEffect(() => {
    load()
  }, [load])

  const requestByDataset = useMemo(() => {
    const map = new Map<number, ExchangeRequest>()
    for (const request of requests) {
      const current = map.get(request.dataset_id)
      if (!current || request.id > current.id) map.set(request.dataset_id, request)
    }
    return map
  }, [requests])

  const stats = useMemo(() => {
    const list = items ?? []
    return {
      total: list.length,
      personal: list.filter((item) => item.data_class === 'Personal').length,
      rows: list.reduce((sum, item) => sum + item.row_count, 0),
    }
  }, [items])

  const submitRequest = async () => {
    if (!selected) return
    setSubmitting(true)
    setError(null)
    setNotice(null)
    try {
      const created = await createExchangeRequest(selected.dataset_id, purpose)
      setRequests((prev) => [created, ...prev])
      setNotice(
        `Запит на «${selected.name}» створено. Data Provider ухвалить рішення; після схвалення файл з’явиться у «Мої запити».`,
      )
      setSelected(null)
      setPurpose('analytics')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не вдалося створити запит'
      setError(
        err instanceof ApiError && err.status === 409
          ? 'Активний запит на цей набір уже існує — перегляньте його у «Мої запити».'
          : message,
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <div className="page-header page-header--row">
        <div className="page-header">
          <h1>{isConsumer ? 'Каталог' : 'Каталог (метадані)'}</h1>
          <p className="subtitle">
            Лише опубліковані набори. Сирі файли та PII у каталозі не показуються.
          </p>
        </div>
        <button type="button" className="btn btn--secondary" onClick={load} disabled={!items}>
          Оновити
        </button>
      </div>

      <div className="stats">
        <div className="stat">
          <span className="stat__label">Опубліковано наборів</span>
          <span className="stat__value stat__value--ok">{integer.format(stats.total)}</span>
        </div>
        <div className="stat">
          <span className="stat__label">З класом Personal</span>
          <span className="stat__value stat__value--warn">{integer.format(stats.personal)}</span>
        </div>
        <div className="stat">
          <span className="stat__label">Рядків у каталозі</span>
          <span className="stat__value">{integer.format(stats.rows)}</span>
        </div>
      </div>

      {notice && (
        <div className="alert alert--success" role="status">
          <div className="alert__body">
            <span className="alert__title">Запит створено</span>
            <span>{notice}</span>
          </div>
        </div>
      )}
      {error && <ErrorMessage title="Не вдалося виконати дію">{error}</ErrorMessage>}

      {!error && items === null && <p className="subtitle">Завантаження…</p>}

      {items !== null && items.length === 0 && (
        <div className="empty">
          <h2>Каталог порожній</h2>
          <p>Опубліковані Data Provider набори з’являться тут після проходження publication gate.</p>
        </div>
      )}

      {items !== null && items.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">ID</th>
                <th scope="col">Назва набору</th>
                <th scope="col">Клас</th>
                <th scope="col">Data Provider</th>
                <th scope="col">Рядки / колонки</th>
                <th scope="col">Quality Score</th>
                <th scope="col">Опубліковано</th>
                <th scope="col">Retention</th>
                <th scope="col">Дії</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const ownRequest = requestByDataset.get(item.dataset_id)
                return (
                  <tr key={item.dataset_id}>
                    <td className="cell-muted">{item.dataset_id}</td>
                    <td className="cell-strong">{item.name}</td>
                    <td>
                      <ClassBadge value={item.data_class} />
                    </td>
                    <td className="cell-muted">{item.provider}</td>
                    <td>
                      {integer.format(item.row_count)} / {item.column_count}
                    </td>
                    <td>
                      <QualityScore score={item.quality_score} />
                    </td>
                    <td className="cell-muted">{formatDate(item.published_at)}</td>
                    <td className="cell-muted">{formatDate(item.retention_until)}</td>
                    <td>
                      {!isConsumer ? (
                        <span className="cell-muted">—</span>
                      ) : ownRequest ? (
                        <span className={`badge badge--status ${requestTone(ownRequest.status)}`}>
                          <span className="badge__dot" aria-hidden="true" />
                          {EXCHANGE_STATUS_LABELS[ownRequest.status] ?? ownRequest.status}
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="btn btn--secondary btn--sm"
                          onClick={() => {
                            setSelected(item)
                            setNotice(null)
                            setError(null)
                          }}
                        >
                          Запросити доступ
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <section className="card" aria-labelledby="request-title">
          <div className="page-header">
            <h2 id="request-title">Запит на доступ: {selected.name}</h2>
            <p className="subtitle">
              Вкажіть мету обробки. Вона має збігатися з активною правовою підставою набору.
            </p>
          </div>
          <label className="filter-select-label" htmlFor="request-purpose">
            <span>Мета обробки:</span>
            <select
              id="request-purpose"
              className="filter-select"
              value={purpose}
              onChange={(event) => setPurpose(event.target.value as LegalBasisPurpose)}
            >
              {PURPOSES.map((value) => (
                <option key={value} value={value}>
                  {LEGAL_BASIS_PURPOSE_LABELS[value]}
                </option>
              ))}
            </select>
          </label>
          <div className="actions">
            <button
              type="button"
              className="btn"
              onClick={submitRequest}
              disabled={submitting}
            >
              {submitting ? 'Надсилання…' : 'Надіслати запит'}
            </button>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => setSelected(null)}
              disabled={submitting}
            >
              Скасувати
            </button>
          </div>
        </section>
      )}
    </>
  )
}
