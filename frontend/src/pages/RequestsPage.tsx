import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { downloadExchangeFile, fetchExchangeRequests } from '../api/exchange'
import {
  LEGAL_BASIS_PURPOSE_LABELS,
  type ExchangeRequest,
} from '../api/types'
import { useAuth } from '../auth/useAuth'
import { ExchangeStatusBadge } from '../components/Badges'
import { Button } from '../components/Button'
import { ErrorMessage } from '../components/ErrorMessage'
import {
  IconAlert,
  IconDatabase,
  IconDownload,
  IconRefresh,
  IconX,
} from '../components/icons'

export default function RequestsPage() {
  const { role } = useAuth()
  const isConsumer = role === 'DataConsumer'
  const isProvider = role === 'DataProvider'

  const [requests, setRequests] = useState<ExchangeRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Download state: track which request ID is currently downloading
  const [downloadingId, setDownloadingId] = useState<number | null>(null)
  const [downloadError, setDownloadError] = useState<{ id: number; message: string } | null>(null)
  const [downloadSuccess, setDownloadSuccess] = useState<number | null>(null)

  const loadRequests = useCallback(async () => {
    setLoading(true)
    setError(null)
    setDownloadError(null)
    try {
      const data = await fetchExchangeRequests()
      setRequests(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося завантажити запити')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadRequests()
  }, [loadRequests])

  const stats = useMemo(() => {
    const total = requests.length
    const pending = requests.filter((r) => r.status === 'pending' || r.status === 'Requested').length
    const approved = requests.filter(
      (r) =>
        r.status === 'approved' ||
        r.status === 'downloaded' ||
        r.status === 'Approved' ||
        r.status === 'Downloaded',
    ).length
    const rejected = requests.filter((r) => r.status === 'rejected' || r.status === 'Rejected').length
    return { total, pending, approved, rejected }
  }, [requests])

  const handleDownload = async (req: ExchangeRequest) => {
    setDownloadingId(req.id)
    setDownloadError(null)
    setDownloadSuccess(null)
    try {
      const fileName = `clean_dataset_${req.dataset_name ?? req.dataset_id}.csv`
      await downloadExchangeFile(req.id, fileName)
      setDownloadSuccess(req.id)
      setRequests((prev) =>
        prev.map((r) => (r.id === req.id ? { ...r, status: 'downloaded' } : r)),
      )
    } catch (err) {
      setDownloadError({
        id: req.id,
        message: err instanceof Error ? err.message : 'Помилка при завантаженні файлу',
      })
    } finally {
      setDownloadingId(null)
    }
  }

  const getPurposeLabel = (purpose: string) => {
    return (LEGAL_BASIS_PURPOSE_LABELS as Record<string, string>)[purpose] ?? purpose
  }

  return (
    <div className="requests-page">
      <div className="page-header page-header--row">
        <div>
          <h1 className="page-title">
            {isConsumer ? 'Мої запити на доступ' : 'Запити на обмін даними'}
          </h1>
          <p className="page-subtitle">
            {isConsumer
              ? 'Відстеження статусів запитів на отримання наборів даних та завантаження очищених копій'
              : 'Вхідні запити на доступ до ваших наборів даних від споживачів'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          {isProvider && (
            <Link to="/access" className="button button--secondary">
              Перейти до схвалення запитів
            </Link>
          )}
          <Button variant="secondary" onClick={loadRequests} disabled={loading} title="Оновити список">
            <IconRefresh size={14} className={loading ? 'icon-spin' : ''} />
            <span>Оновити</span>
          </Button>
        </div>
      </div>

      {/* Статистичні картки */}
      <div className="stats stats--4cols" style={{ marginTop: 'var(--space-4)' }}>
        <div className="stat-card">
          <span className="stat-card__label">Всього запитів</span>
          <strong className="stat-card__value">{stats.total}</strong>
        </div>
        <div className="stat-card">
          <span className="stat-card__label">Очікують розгляду</span>
          <strong className="stat-card__value" style={{ color: 'var(--color-warning)' }}>
            {stats.pending}
          </strong>
        </div>
        <div className="stat-card">
          <span className="stat-card__label">Схвалено / Доступно</span>
          <strong className="stat-card__value" style={{ color: 'var(--color-success)' }}>
            {stats.approved}
          </strong>
        </div>
        <div className="stat-card">
          <span className="stat-card__label">Відхилено</span>
          <strong className="stat-card__value" style={{ color: 'var(--color-danger)' }}>
            {stats.rejected}
          </strong>
        </div>
      </div>

      {error && (
        <div style={{ marginTop: 'var(--space-4)' }}>
          <ErrorMessage title="Помилка завантаження запитів">{error}</ErrorMessage>
        </div>
      )}

      {/* Повідомлення про помилку завантаження */}
      {downloadError && (
        <div className="alert-banner alert-banner--danger" style={{ marginTop: 'var(--space-4)' }}>
          <IconAlert size={18} />
          <div style={{ flex: 1 }}>
            <strong>Помилка завантаження набору (запит #{downloadError.id}):</strong>{' '}
            {downloadError.message}
          </div>
          <button
            type="button"
            className="alert-close"
            onClick={() => setDownloadError(null)}
            aria-label="Закрити"
          >
            <IconX size={14} />
          </button>
        </div>
      )}

      {loading && requests.length === 0 ? (
        <div className="empty" style={{ minHeight: '260px', marginTop: 'var(--space-5)' }}>
          <p>Завантаження запитів на доступ...</p>
        </div>
      ) : requests.length === 0 ? (
        <div className="empty" style={{ minHeight: '260px', marginTop: 'var(--space-5)' }}>
          <IconDatabase size={40} style={{ opacity: 0.4, marginBottom: 'var(--space-2)' }} />
          <h3>Запитів на доступ не знайдено</h3>
          <p>
            {isConsumer
              ? 'Ви ще не надсилали запитів на доступ до опублікованих наборів даних.'
              : 'На ваші опубліковані набори даних поки немає вхідних запитів.'}
          </p>
          {isConsumer && (
            <div style={{ marginTop: 'var(--space-3)' }}>
              <Link to="/catalog" className="button button--primary">
                Перейти до Каталогу
              </Link>
            </div>
          )}
        </div>
      ) : (
        <div className="card" style={{ marginTop: 'var(--space-5)', overflow: 'hidden' }}>
          <div className="table-responsive">
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: '60px' }}>#</th>
                  <th>Набір даних</th>
                  {!isConsumer && <th>Споживач</th>}
                  <th>Мета використання</th>
                  <th>Дата створення</th>
                  <th>Статус</th>
                  <th>Коментар Data Steward</th>
                  <th style={{ textAlign: 'right' }}>Дії</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((req) => {
                  const statusStr = String(req.status).toLowerCase()
                  const isApproved = statusStr === 'approved' || statusStr === 'downloaded'
                  const isPending = statusStr === 'pending' || statusStr === 'requested'
                  const isDownloading = downloadingId === req.id
                  const isDownloaded = statusStr === 'downloaded' || downloadSuccess === req.id

                  return (
                    <tr key={req.id}>
                      <td className="caption" style={{ fontWeight: 600 }}>
                        {req.id}
                      </td>
                      <td>
                        <strong>{req.dataset_name ?? `Набір #${req.dataset_id}`}</strong>
                      </td>
                      {!isConsumer && (
                        <td>
                          <span className="caption">{req.consumer_email ?? req.consumer_id}</span>
                        </td>
                      )}
                      <td>
                        <span className="purpose-tag">{getPurposeLabel(req.purpose)}</span>
                      </td>
                      <td className="caption">
                        {req.created_at ? new Date(req.created_at).toLocaleDateString('uk-UA') : '—'}
                      </td>
                      <td>
                        <ExchangeStatusBadge value={req.status} />
                      </td>
                      <td>
                        {req.review_comment ? (
                          <span className="review-comment">{req.review_comment}</span>
                        ) : (
                          <span className="caption text-muted">—</span>
                        )}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        {isConsumer && isApproved && (
                          <Button
                            variant={isDownloaded ? 'secondary' : 'primary'}
                            onClick={() => handleDownload(req)}
                            disabled={isDownloading}
                            title="Завантажити clean-копію набору"
                          >
                            <IconDownload size={14} className={isDownloading ? 'icon-spin' : ''} />
                            <span>
                              {isDownloading
                                ? 'Завантаження...'
                                : isDownloaded
                                  ? 'Завантажити ще раз'
                                  : 'Завантажити'}
                            </span>
                          </Button>
                        )}
                        {isConsumer && isPending && (
                          <span className="caption text-muted" title="Запит очікує схвалення">
                            Очікує рішення
                          </span>
                        )}
                        {isConsumer && statusStr === 'rejected' && (
                          <span className="caption text-danger" title="Запит відхилено">
                            Відхилено
                          </span>
                        )}
                        {!isConsumer && (
                          <Link to="/access" className="button button--secondary button--sm">
                            Переглянути в черзі
                          </Link>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
