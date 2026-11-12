import { useEffect, useMemo, useState } from 'react'
import {
  approveExchangeRequest,
  fetchExchangeRequests,
  rejectExchangeRequest,
} from '../api/exchange'
import {
  EXCHANGE_STATUS_LABELS,
  LEGAL_BASIS_PURPOSE_LABELS,
  type ExchangeRequest,
} from '../api/types'
import { ErrorMessage } from '../components/ErrorMessage'

const formatDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString('uk-UA') : '—'

const formatDateTime = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString('uk-UA', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—'

const statusTone = (status: ExchangeRequest['status']): string => {
  if (status === 'Approved' || status === 'Downloaded') return 'badge--published'
  if (status === 'Requested') return 'badge--attention'
  return 'badge--expired'
}

const defaultAccessUntil = () => {
  const date = new Date()
  date.setDate(date.getDate() + 30)
  return date.toISOString().slice(0, 10)
}

type DecisionMode = 'approve' | 'reject'

export default function AccessRequestsPage() {
  const [rows, setRows] = useState<ExchangeRequest[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [selected, setSelected] = useState<ExchangeRequest | null>(null)
  const [mode, setMode] = useState<DecisionMode>('approve')
  const [accessUntil, setAccessUntil] = useState(defaultAccessUntil())
  const [comment, setComment] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [statusFilter, setStatusFilter] = useState<'pending' | 'all'>('pending')

  const load = () => {
    setError(null)
    fetchExchangeRequests()
      .then(setRows)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : 'Не вдалося завантажити запити'),
      )
  }

  useEffect(() => {
    load()
  }, [])

  const visible = useMemo(() => {
    const list = rows ?? []
    return statusFilter === 'pending'
      ? list.filter((row) => row.status === 'Requested')
      : list
  }, [rows, statusFilter])

  const stats = useMemo(() => {
    const list = rows ?? []
    return {
      pending: list.filter((row) => row.status === 'Requested').length,
      approved: list.filter((row) => row.status === 'Approved').length,
      total: list.length,
    }
  }, [rows])

  const openDecision = (request: ExchangeRequest, nextMode: DecisionMode) => {
    setSelected(request)
    setMode(nextMode)
    setAccessUntil(defaultAccessUntil())
    setComment('')
    setError(null)
    setNotice(null)
  }

  const submit = async () => {
    if (!selected) return
    setSubmitting(true)
    setError(null)
    setNotice(null)
    try {
      const updated =
        mode === 'approve'
          ? await approveExchangeRequest(selected.id, accessUntil, comment.trim() || undefined)
          : await rejectExchangeRequest(selected.id, comment.trim())
      setRows((prev) =>
        (prev ?? []).map((row) => (row.id === updated.id ? updated : row)),
      )
      setNotice(
        mode === 'approve'
          ? `Запит №${updated.id} схвалено. Доступ до ${formatDate(updated.access_until)}.`
          : `Запит №${updated.id} відхилено.`,
      )
      setSelected(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося ухвалити рішення')
    } finally {
      setSubmitting(false)
    }
  }

  const canSubmit = mode === 'approve' || comment.trim().length > 0

  return (
    <>
      <div className="page-header page-header--row">
        <div className="page-header">
          <h1>Запити на доступ</h1>
          <p className="subtitle">
            Вхідні запити до ваших наборів. Рішення ухвалює лише власник набору.
          </p>
        </div>
        <button type="button" className="btn btn--secondary" onClick={load} disabled={!rows}>
          Оновити
        </button>
      </div>

      <div className="stats">
        <div className="stat">
          <span className="stat__label">Очікують рішення</span>
          <span className="stat__value stat__value--warn">{stats.pending}</span>
        </div>
        <div className="stat">
          <span className="stat__label">Активний доступ</span>
          <span className="stat__value stat__value--ok">{stats.approved}</span>
        </div>
        <div className="stat">
          <span className="stat__label">Усього запитів</span>
          <span className="stat__value">{stats.total}</span>
        </div>
      </div>

      {notice && (
        <div className="alert alert--success" role="status">
          <div className="alert__body">
            <span className="alert__title">Рішення збережено</span>
            <span>{notice}</span>
          </div>
        </div>
      )}
      {error && <ErrorMessage title="Не вдалося виконати дію">{error}</ErrorMessage>}
      {!error && rows === null && <p className="subtitle">Завантаження…</p>}

      {selected && (
        <section className="card" aria-labelledby="decision-title">
          <div className="page-header">
            <h2 id="decision-title">
              {mode === 'approve' ? 'Схвалити' : 'Відхилити'} запит №{selected.id}
            </h2>
            <p className="subtitle">
              Набір «{selected.dataset_name}», мета:{' '}
              {LEGAL_BASIS_PURPOSE_LABELS[selected.purpose] ?? selected.purpose}. Заявник:{' '}
              {selected.requester_email}.
            </p>
          </div>

          {mode === 'approve' ? (
            <label className="filter-select-label" htmlFor="access-until">
              <span>Доступ до:</span>
              <input
                id="access-until"
                type="date"
                className="filter-select"
                value={accessUntil}
                min={new Date().toISOString().slice(0, 10)}
                onChange={(event) => setAccessUntil(event.target.value)}
              />
            </label>
          ) : null}

          <label className="filter-select-label" htmlFor="decision-comment">
            <span>{mode === 'approve' ? 'Коментар (необов’язково):' : 'Причина відхилення:'}</span>
            <input
              id="decision-comment"
              type="text"
              className="filter-select"
              maxLength={500}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder={mode === 'approve' ? 'Наприклад: погоджено в межах договору' : 'Опишіть причину'}
            />
          </label>

          <div className="actions">
            <button
              type="button"
              className={mode === 'approve' ? 'btn' : 'btn btn--danger-soft'}
              onClick={submit}
              disabled={submitting || !canSubmit}
            >
              {submitting
                ? 'Збереження…'
                : mode === 'approve'
                  ? 'Схвалити запит'
                  : 'Відхилити запит'}
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

      {rows !== null && (
        <section className="card card--table-section">
          <div className="table-toolbar">
            <div className="table-toolbar__filters">
              <label className="filter-select-label">
                <span>Показати:</span>
                <select
                  className="filter-select"
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value as 'pending' | 'all')}
                >
                  <option value="pending">Лише ті, що очікують ({stats.pending})</option>
                  <option value="all">Усі ({stats.total})</option>
                </select>
              </label>
            </div>
          </div>

          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">Набір</th>
                  <th scope="col">Заявник</th>
                  <th scope="col">Мета</th>
                  <th scope="col">Подано</th>
                  <th scope="col">Статус</th>
                  <th scope="col">Доступ до</th>
                  <th scope="col">Дії</th>
                </tr>
              </thead>
              <tbody>
                {visible.length === 0 ? (
                  <tr>
                    <td className="table__empty" colSpan={8}>
                      {stats.total === 0
                        ? 'Вхідних запитів ще немає'
                        : 'Немає запитів, що очікують рішення'}
                    </td>
                  </tr>
                ) : (
                  visible.map((row) => (
                    <tr key={row.id}>
                      <td className="cell-muted">{row.id}</td>
                      <td className="cell-strong">{row.dataset_name}</td>
                      <td>{row.requester_email}</td>
                      <td>{LEGAL_BASIS_PURPOSE_LABELS[row.purpose] ?? row.purpose}</td>
                      <td className="cell-muted">{formatDateTime(row.requested_at)}</td>
                      <td>
                        <span className={`badge badge--status ${statusTone(row.status)}`}>
                          <span className="badge__dot" aria-hidden="true" />
                          {EXCHANGE_STATUS_LABELS[row.status] ?? row.status}
                        </span>
                      </td>
                      <td className="cell-muted">{formatDate(row.access_until)}</td>
                      <td>
                        {row.status === 'Requested' ? (
                          <div className="actions">
                            <button
                              type="button"
                              className="btn btn--sm"
                              onClick={() => openDecision(row, 'approve')}
                            >
                              Схвалити
                            </button>
                            <button
                              type="button"
                              className="btn btn--danger-soft"
                              onClick={() => openDecision(row, 'reject')}
                            >
                              Відхилити
                            </button>
                          </div>
                        ) : (
                          <span className="cell-muted">
                            {row.review_comment || 'Рішення ухвалено'}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  )
}
