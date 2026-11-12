import { useEffect, useMemo, useState } from 'react'
import { downloadExchangeFile, fetchExchangeRequests } from '../api/exchange'
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

export default function RequestsPage() {
  const [rows, setRows] = useState<ExchangeRequest[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<number | null>(null)

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

  const stats = useMemo(() => {
    const list = rows ?? []
    return {
      total: list.length,
      pending: list.filter((row) => row.status === 'Requested').length,
      available: list.filter((row) => row.status === 'Approved' || row.status === 'Downloaded').length,
    }
  }, [rows])

  const download = async (request: ExchangeRequest) => {
    setDownloading(request.id)
    setError(null)
    setNotice(null)
    try {
      await downloadExchangeFile(request.id, `dataset-${request.dataset_id}.csv`)
      setNotice(`Файл «${request.dataset_name}» завантажено. Подія DOWNLOAD записана в аудит.`)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося завантажити файл')
    } finally {
      setDownloading(null)
    }
  }

  return (
    <>
      <div className="page-header page-header--row">
        <div className="page-header">
          <h1>Мої запити</h1>
          <p className="subtitle">
            Запити на доступ до опублікованих наборів. Завантажується лише очищена версія.
          </p>
        </div>
        <button type="button" className="btn btn--secondary" onClick={load} disabled={!rows}>
          Оновити
        </button>
      </div>

      <div className="stats">
        <div className="stat">
          <span className="stat__label">Усього запитів</span>
          <span className="stat__value">{stats.total}</span>
        </div>
        <div className="stat">
          <span className="stat__label">Очікують рішення</span>
          <span className="stat__value stat__value--warn">{stats.pending}</span>
        </div>
        <div className="stat">
          <span className="stat__label">Доступні до завантаження</span>
          <span className="stat__value stat__value--ok">{stats.available}</span>
        </div>
      </div>

      {notice && (
        <div className="alert alert--success" role="status">
          <div className="alert__body">
            <span className="alert__title">Готово</span>
            <span>{notice}</span>
          </div>
        </div>
      )}
      {error && <ErrorMessage title="Не вдалося виконати дію">{error}</ErrorMessage>}
      {!error && rows === null && <p className="subtitle">Завантаження…</p>}

      {rows !== null && rows.length === 0 && (
        <div className="empty">
          <h2>Запитів ще немає</h2>
          <p>Знайдіть потрібний набір у каталозі та надішліть запит на доступ.</p>
        </div>
      )}

      {rows !== null && rows.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">ID</th>
                <th scope="col">Набір</th>
                <th scope="col">Мета</th>
                <th scope="col">Статус</th>
                <th scope="col">Подано</th>
                <th scope="col">Рішення</th>
                <th scope="col">Доступ до</th>
                <th scope="col">Коментар</th>
                <th scope="col">Дії</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const canDownload = row.status === 'Approved' || row.status === 'Downloaded'
                return (
                  <tr key={row.id}>
                    <td className="cell-muted">{row.id}</td>
                    <td className="cell-strong">{row.dataset_name}</td>
                    <td>{LEGAL_BASIS_PURPOSE_LABELS[row.purpose] ?? row.purpose}</td>
                    <td>
                      <span className={`badge badge--status ${statusTone(row.status)}`}>
                        <span className="badge__dot" aria-hidden="true" />
                        {EXCHANGE_STATUS_LABELS[row.status] ?? row.status}
                      </span>
                    </td>
                    <td className="cell-muted">{formatDateTime(row.requested_at)}</td>
                    <td className="cell-muted">{formatDateTime(row.decided_at)}</td>
                    <td className="cell-muted">{formatDate(row.access_until)}</td>
                    <td className="cell-muted">{row.review_comment || '—'}</td>
                    <td>
                      {canDownload ? (
                        <button
                          type="button"
                          className="btn btn--secondary btn--sm"
                          onClick={() => download(row)}
                          disabled={downloading === row.id}
                        >
                          {downloading === row.id ? 'Завантаження…' : 'Завантажити'}
                        </button>
                      ) : (
                        <span className="cell-muted">—</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
