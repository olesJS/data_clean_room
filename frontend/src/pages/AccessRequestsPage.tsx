import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  approveExchangeRequest,
  fetchExchangeRequests,
  fetchLegalBasis,
  rejectExchangeRequest,
  revokeLegalBasis,
} from '../api/exchange'
import {
  LEGAL_BASIS_PURPOSE_LABELS,
  LEGAL_BASIS_TYPE_LABELS,
  type ExchangeRequest,
  type ExchangeRequestStatus,
  type LegalBasis,
} from '../api/types'
import { useAuth } from '../auth/useAuth'
import { ExchangeStatusBadge } from '../components/Badges'
import { Button } from '../components/Button'
import { ErrorMessage } from '../components/ErrorMessage'
import {
  IconAlert,
  IconCheck,
  IconRefresh,
  IconShield,
  IconX,
} from '../components/icons'

function format409Reason(message: string): string {
  if (message.includes('revoked')) {
    return 'Згоду субʼєкта даних відкликано — схвалення неможливе (UC-12).'
  }
  if (message.includes('purpose_mismatch')) {
    return 'Мета запиту не відповідає дозволеній правовій підставі набору.'
  }
  if (message.includes('no_legal_basis')) {
    return 'Для цього набору відсутня чинна правова підстава.'
  }
  if (message.includes('expired')) {
    return 'Термін дії правової підстави вичерпано.'
  }
  return message
}

export default function AccessRequestsPage() {
  const { role } = useAuth()
  const isSteward = role === 'DataSteward'
  const isProvider = role === 'DataProvider'

  const [requests, setRequests] = useState<ExchangeRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filter: 'all' | 'pending' | 'approved' | 'rejected'
  const [statusFilter, setStatusFilter] = useState<'all' | 'pending' | 'approved' | 'rejected'>('pending')

  // Modals state
  const [approveTarget, setApproveTarget] = useState<ExchangeRequest | null>(null)
  const [approveComment, setApproveComment] = useState('')
  const [approveSubmitting, setApproveSubmitting] = useState(false)
  const [approveError, setApproveError] = useState<string | null>(null)

  const [rejectTarget, setRejectTarget] = useState<ExchangeRequest | null>(null)
  const [rejectComment, setRejectComment] = useState('')
  const [rejectSubmitting, setRejectSubmitting] = useState(false)
  const [rejectError, setRejectError] = useState<string | null>(null)

  // UC-12: Consent Revocation panel / demo state
  const [activeTab, setActiveTab] = useState<'requests' | 'consents'>('requests')
  const [consentDatasetId, setConsentDatasetId] = useState('1')
  const [consentLegalBasis, setConsentLegalBasis] = useState<LegalBasis | null>(null)
  const [consentLoading, setConsentLoading] = useState(false)
  const [consentError, setConsentError] = useState<string | null>(null)
  const [consentRevoking, setConsentRevoking] = useState(false)
  const [showRevokeModal, setShowRevokeModal] = useState(false)
  const [revokeReason, setRevokeReason] = useState('')

  const loadRequests = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchExchangeRequests()
      setRequests(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося завантажити запити на доступ')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadRequests()
  }, [loadRequests])

  const loadConsentData = useCallback(async (dId: string) => {
    setConsentLoading(true)
    setConsentError(null)
    try {
      const lb = await fetchLegalBasis(dId)
      setConsentLegalBasis(lb[0] ?? null)
    } catch (err) {
      setConsentError(err instanceof Error ? err.message : 'Не вдалося завантажити правову підставу')
    } finally {
      setConsentLoading(false)
    }
  }, [])

  useEffect(() => {
    if (activeTab === 'consents') {
      loadConsentData(consentDatasetId)
    }
  }, [activeTab, consentDatasetId, loadConsentData])

  const filteredRequests = useMemo(() => {
    if (statusFilter === 'all') return requests
    return requests.filter((r) => {
      const s = String(r.status).toLowerCase()
      if (statusFilter === 'pending') return s === 'pending' || s === 'requested'
      if (statusFilter === 'approved') return s === 'approved' || s === 'downloaded'
      if (statusFilter === 'rejected') return s === 'rejected'
      return s === statusFilter
    })
  }, [requests, statusFilter])

  // Count stats
  const pendingCount = useMemo(
    () =>
      requests.filter((r) => {
        const s = String(r.status).toLowerCase()
        return s === 'pending' || s === 'requested'
      }).length,
    [requests],
  )
  const approvedCount = useMemo(
    () =>
      requests.filter((r) => {
        const s = String(r.status).toLowerCase()
        return s === 'approved' || s === 'downloaded'
      }).length,
    [requests],
  )
  const rejectedCount = useMemo(
    () =>
      requests.filter((r) => {
        const s = String(r.status).toLowerCase()
        return s === 'rejected'
      }).length,
    [requests],
  )

  // Open Approve Modal
  const openApproveModal = (req: ExchangeRequest) => {
    setApproveTarget(req)
    setApproveComment('')
    setApproveError(null)
  }

  // Open Reject Modal
  const openRejectModal = (req: ExchangeRequest) => {
    setRejectTarget(req)
    setRejectComment('')
    setRejectError(null)
  }

  const handleApprove = async () => {
    if (!approveTarget) return
    setApproveSubmitting(true)
    setApproveError(null)
    try {
      await approveExchangeRequest(approveTarget.id, approveComment || undefined)
      setApproveTarget(null)
      await loadRequests()
    } catch (err) {
      const rawMsg = err instanceof Error ? err.message : 'Не вдалося схвалити запит'
      setApproveError(format409Reason(rawMsg))
    } finally {
      setApproveSubmitting(false)
    }
  }

  const handleReject = async () => {
    if (!rejectTarget) return
    if (!rejectComment.trim()) {
      setRejectError('Вкажіть причину відхилення запиту')
      return
    }
    setRejectSubmitting(true)
    setRejectError(null)
    try {
      await rejectExchangeRequest(rejectTarget.id, rejectComment.trim())
      setRejectTarget(null)
      await loadRequests()
    } catch (err) {
      setRejectError(err instanceof Error ? err.message : 'Не вдалося відхилити запит')
    } finally {
      setRejectSubmitting(false)
    }
  }

  const handleRevokeConsent = async () => {
    if (!consentDatasetId || !consentLegalBasis) return
    setConsentRevoking(true)
    try {
      await revokeLegalBasis(consentLegalBasis.id, revokeReason || undefined)
      setShowRevokeModal(false)
      setRevokeReason('')
      await loadConsentData(consentDatasetId)
    } catch (err) {
      setConsentError(err instanceof Error ? err.message : 'Не вдалося відкликати згоду')
    } finally {
      setConsentRevoking(false)
    }
  }

  const getPurposeLabel = (p: string) => {
    return (LEGAL_BASIS_PURPOSE_LABELS as Record<string, string>)[p] ?? p
  }

  const getTypeLabel = (t: string) => {
    return (LEGAL_BASIS_TYPE_LABELS as Record<string, string>)[t] ?? t
  }

  return (
    <div className="access-requests-page">
      <div className="page-header page-header--row">
        <div>
          <h1 className="page-title">
            {isSteward ? 'Моніторинг запитів на доступ' : 'Запити на доступ до наборів'}
          </h1>
          <p className="page-subtitle">
            {isSteward
              ? 'Черга запитів споживачів (режим перегляду для Data Steward) та керування згодами (UC-12)'
              : 'Черга запитів споживачів: перевірка правової підстави (UC-09, UC-10) та керування згодами (UC-12)'}
          </p>
        </div>
        <Button variant="secondary" onClick={loadRequests} disabled={loading} title="Оновити список">
          <IconRefresh size={14} className={loading ? 'icon-spin' : ''} />
          <span>Оновити</span>
        </Button>
      </div>

      {/* Перемикач вкладок між Запитами та Відкликанням згоди */}
      <div className="profile-tabs" style={{ marginTop: 'var(--space-4)' }}>
        <button
          type="button"
          className={`profile-tabs__item ${activeTab === 'requests' ? 'profile-tabs__item--active' : ''}`}
          onClick={() => setActiveTab('requests')}
        >
          <span>Черга запитів на доступ</span>
          {pendingCount > 0 && <span className="profile-tabs__count">{pendingCount}</span>}
        </button>
        <button
          type="button"
          className={`profile-tabs__item ${activeTab === 'consents' ? 'profile-tabs__item--active' : ''}`}
          onClick={() => setActiveTab('consents')}
        >
          <IconShield size={14} />
          <span>Відкликання згоди (UC-12)</span>
        </button>
      </div>

      {activeTab === 'requests' ? (
        <>
          {/* Фільтри за статусом */}
          <div className="table-toolbar" style={{ marginTop: 'var(--space-4)' }}>
            <div className="tab-pills">
              <button
                type="button"
                className={`tab-pill ${statusFilter === 'pending' ? 'tab-pill--active' : ''}`}
                onClick={() => setStatusFilter('pending')}
              >
                Очікують розгляду ({pendingCount})
              </button>
              <button
                type="button"
                className={`tab-pill ${statusFilter === 'all' ? 'tab-pill--active' : ''}`}
                onClick={() => setStatusFilter('all')}
              >
                Всі запити ({requests.length})
              </button>
              <button
                type="button"
                className={`tab-pill ${statusFilter === 'approved' ? 'tab-pill--active' : ''}`}
                onClick={() => setStatusFilter('approved')}
              >
                Схвалені ({approvedCount})
              </button>
              <button
                type="button"
                className={`tab-pill ${statusFilter === 'rejected' ? 'tab-pill--active' : ''}`}
                onClick={() => setStatusFilter('rejected')}
              >
                Відхилені ({rejectedCount})
              </button>
            </div>
          </div>

          {isSteward && (
            <div className="alert-banner alert-banner--warning" style={{ marginTop: 'var(--space-3)' }}>
              <IconShield size={18} />
              <div>
                <strong>Режим перегляду Data Steward:</strong> Згідно з правилами безпеки, схвалювати або відхиляти запити на доступ може лише власник набору даних (Data Provider). Data Steward має право переглядати всі запити та відкликати згоди субʼєктів даних (UC-12).
              </div>
            </div>
          )}

          {error && (
            <div style={{ marginTop: 'var(--space-4)' }}>
              <ErrorMessage title="Помилка завантаження черги запитів">{error}</ErrorMessage>
            </div>
          )}

          {loading && requests.length === 0 ? (
            <div className="empty" style={{ minHeight: '260px', marginTop: 'var(--space-4)' }}>
              <p>Завантаження черги запитів...</p>
            </div>
          ) : filteredRequests.length === 0 ? (
            <div className="empty" style={{ minHeight: '260px', marginTop: 'var(--space-4)' }}>
              <IconCheck size={40} style={{ opacity: 0.4, marginBottom: 'var(--space-2)' }} />
              <h3>Немає запитів для відображення</h3>
              <p>
                {statusFilter === 'pending'
                  ? 'Усі вхідні запити на доступ уже опрацьовано.'
                  : 'За вибраним фільтром запитів не знайдено.'}
              </p>
            </div>
          ) : (
            <div className="card" style={{ marginTop: 'var(--space-4)', overflow: 'hidden' }}>
              <div className="table-responsive">
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ width: '60px' }}>#</th>
                      <th>Запитувач</th>
                      <th>Набір даних</th>
                      <th>Мета використання</th>
                      <th>Дата запиту</th>
                      <th>Статус</th>
                      <th>Коментар</th>
                      <th style={{ textAlign: 'right' }}>{isProvider ? 'Рішення' : 'Стан'}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRequests.map((req) => {
                      const s = String(req.status).toLowerCase()
                      const isPending = s === 'pending' || s === 'requested'

                      return (
                        <tr key={req.id}>
                          <td className="caption" style={{ fontWeight: 600 }}>
                            {req.id}
                          </td>
                          <td>
                            <strong>{req.consumer_email ?? `Споживач #${req.consumer_id}`}</strong>
                            <div className="caption text-muted">ID: {req.consumer_id}</div>
                          </td>
                          <td>
                            <strong>{req.dataset_name ?? `Набір #${req.dataset_id}`}</strong>
                          </td>
                          <td>
                            <span className="purpose-tag">{getPurposeLabel(req.purpose)}</span>
                          </td>
                          <td className="caption">
                            {req.created_at ? new Date(req.created_at).toLocaleDateString('uk-UA') : '—'}
                          </td>
                          <td>
                            <ExchangeStatusBadge value={req.status as ExchangeRequestStatus} />
                          </td>
                          <td>
                            {req.review_comment ? (
                              <span className="review-comment">{req.review_comment}</span>
                            ) : (
                              <span className="caption text-muted">—</span>
                            )}
                          </td>
                          <td style={{ textAlign: 'right' }}>
                            {isPending ? (
                              isProvider ? (
                                <div style={{ display: 'flex', gap: 'var(--space-1)', justifyContent: 'flex-end' }}>
                                  <Button
                                    variant="primary"
                                    onClick={() => openApproveModal(req)}
                                    style={{ padding: '6px 12px', fontSize: '13px' }}
                                  >
                                    Схвалити
                                  </Button>
                                  <Button
                                    variant="secondary"
                                    onClick={() => openRejectModal(req)}
                                    style={{ padding: '6px 12px', fontSize: '13px', color: 'var(--color-danger)' }}
                                  >
                                    Відхилити
                                  </Button>
                                </div>
                              ) : (
                                <span className="caption text-muted" title="Схвалювати або відхиляти запит може лише власник набору (DataProvider)">
                                  Очікує рішення власника
                                </span>
                              )
                            ) : (
                              <span className="caption text-muted">Опрацьовано</span>
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
        </>
      ) : (
        /* Вкладка UC-12: Керування та відкликання згоди */
        <div style={{ marginTop: 'var(--space-4)' }}>
          <div className="card" style={{ padding: 'var(--space-5)' }}>
            <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: 'var(--space-2)' }}>
              Перевірка та відкликання згоди субʼєкта даних (UC-12)
            </h3>
            <p className="caption" style={{ marginBottom: 'var(--space-4)' }}>
              Відповідно до GDPR ст. 7(3), субʼєкт даних має право відкликати згоду в будь-який момент. Після відкликання згоди схвалення нових запитів блокується (409), а завантаження файлів для попередньо схвалених запитів забороняється (403).
            </p>

            <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
              <label htmlFor="consent-dataset-select" style={{ fontWeight: 500, fontSize: '14px' }}>
                Виберіть набір даних:
              </label>
              <select
                id="consent-dataset-select"
                className="form-select"
                style={{ width: '260px' }}
                value={consentDatasetId}
                onChange={(e) => setConsentDatasetId(e.target.value)}
              >
                <option value="1">1: clean_dataset_customers.csv</option>
                <option value="2">2: clean_dataset_financials.csv</option>
                <option value="3">3: dataset_anonymized_preview.csv</option>
              </select>
              <Button
                variant="secondary"
                onClick={() => loadConsentData(consentDatasetId)}
                disabled={consentLoading}
              >
                <IconRefresh size={14} className={consentLoading ? 'icon-spin' : ''} />
                <span>Оновити</span>
              </Button>
            </div>

            {consentError && (
              <div style={{ marginBottom: 'var(--space-3)' }}>
                <ErrorMessage title="Помилка завантаження правової підстави">{consentError}</ErrorMessage>
              </div>
            )}

            {consentLoading ? (
              <p className="caption">Завантаження інформації про правову підставу...</p>
            ) : !consentLegalBasis ? (
              <div className="alert-banner alert-banner--warning">
                <IconAlert size={18} />
                <div>Для цього набору даних правова підстава ще не зареєстрована.</div>
              </div>
            ) : (
              <div
                className="legal-basis-detail-card"
                style={{
                  border: '1px solid var(--color-line)',
                  borderRadius: 'var(--radius-md)',
                  padding: 'var(--space-4)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <h4 style={{ fontSize: '16px', fontWeight: 600, marginBottom: 'var(--space-1)' }}>
                      Підстава: {getTypeLabel(consentLegalBasis.type)}
                    </h4>
                    <p className="caption">
                      Документ: <strong>{consentLegalBasis.document_ref}</strong> · Мета:{' '}
                      <strong>{getPurposeLabel(consentLegalBasis.purpose)}</strong>
                    </p>
                  </div>
                  <div>
                    {consentLegalBasis.revoked_at ? (
                      <span className="badge badge--status badge--expired">
                        <span className="badge__dot" aria-hidden="true" />
                        Згоду відкликано
                      </span>
                    ) : consentLegalBasis.is_active ? (
                      <span className="badge badge--status badge--published">
                        <span className="badge__dot" aria-hidden="true" />
                        Чинна
                      </span>
                    ) : (
                      <span className="badge badge--status badge--expired">
                        <span className="badge__dot" aria-hidden="true" />
                        Неактивна
                      </span>
                    )}
                  </div>
                </div>

                <div
                  style={{
                    marginTop: 'var(--space-3)',
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 'var(--space-2)',
                  }}
                >
                  <div className="caption">
                    Діє до:{' '}
                    <strong>
                      {consentLegalBasis.valid_until
                        ? new Date(consentLegalBasis.valid_until).toLocaleDateString('uk-UA')
                        : 'Безстроково'}
                    </strong>
                  </div>
                  <div className="caption">
                    Дата реєстрації:{' '}
                    <strong>
                      {consentLegalBasis.created_at
                        ? new Date(consentLegalBasis.created_at).toLocaleDateString('uk-UA')
                        : 'Не вказано'}
                    </strong>
                  </div>
                </div>

                {consentLegalBasis.revoked_at && (
                  <div className="alert-banner alert-banner--danger" style={{ marginTop: 'var(--space-3)' }}>
                    <IconAlert size={16} />
                    <div>
                      <strong>Згоду відкликано!</strong> Дата:{' '}
                      {new Date(consentLegalBasis.revoked_at).toLocaleString('uk-UA')}.{' '}
                      {consentLegalBasis.revoked_reason && `Причина: ${consentLegalBasis.revoked_reason}`}
                    </div>
                  </div>
                )}

                {consentLegalBasis.type === 'consent' && !consentLegalBasis.revoked_at && (
                  <div
                    style={{
                      marginTop: 'var(--space-4)',
                      borderTop: '1px solid var(--color-line)',
                      paddingTop: 'var(--space-3)',
                    }}
                  >
                    <Button
                      variant="secondary"
                      onClick={() => setShowRevokeModal(true)}
                      style={{ color: 'var(--color-danger)', borderColor: 'var(--color-danger)' }}
                    >
                      Відкликати згоду
                    </Button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Модальне вікно підтвердження схвалення */}
      {approveTarget && (
        <div className="modal-backdrop" onClick={() => !approveSubmitting && setApproveTarget(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="modal-header">
              <h3 className="modal-title">Схвалення запиту на доступ</h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setApproveTarget(null)}
                disabled={approveSubmitting}
                aria-label="Закрити"
              >
                <IconX size={18} />
              </button>
            </div>

            <div className="modal-body">
              <p>
                Ви надаєте дозвіл користувачу{' '}
                <strong>{approveTarget.consumer_email ?? `Споживач #${approveTarget.consumer_id}`}</strong>{' '}
                на отримання набору <strong>«{approveTarget.dataset_name ?? approveTarget.dataset_id}»</strong>{' '}
                з метою:
              </p>
              <div
                style={{
                  margin: 'var(--space-2) 0',
                  padding: 'var(--space-2) var(--space-3)',
                  background: 'var(--color-light)',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                <strong>{getPurposeLabel(approveTarget.purpose)}</strong>
              </div>

              <div className="form-group" style={{ marginTop: 'var(--space-4)' }}>
                <label htmlFor="approve-comment" className="form-label">
                  Коментар Data Steward (необовʼязково)
                </label>
                <input
                  id="approve-comment"
                  type="text"
                  className="form-input"
                  placeholder="Наприклад: Перевірено, мета відповідає правовій підставі"
                  value={approveComment}
                  onChange={(e) => setApproveComment(e.target.value)}
                  disabled={approveSubmitting}
                />
              </div>

              {approveError && (
                <div className="alert-banner alert-banner--danger" style={{ marginTop: 'var(--space-3)' }}>
                  <IconAlert size={16} />
                  <div>
                    <strong>Відмова в схваленні:</strong> {approveError}
                  </div>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <Button variant="secondary" onClick={() => setApproveTarget(null)} disabled={approveSubmitting}>
                Скасувати
              </Button>
              <Button variant="primary" onClick={handleApprove} disabled={approveSubmitting}>
                {approveSubmitting ? 'Схвалення...' : 'Підтвердити схвалення'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Модальне вікно відхилення */}
      {rejectTarget && (
        <div className="modal-backdrop" onClick={() => !rejectSubmitting && setRejectTarget(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="modal-header">
              <h3 className="modal-title">Відхилення запиту на доступ</h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setRejectTarget(null)}
                disabled={rejectSubmitting}
                aria-label="Закрити"
              >
                <IconX size={18} />
              </button>
            </div>

            <div className="modal-body">
              <p>
                Вкажіть причину відхилення запиту користувача{' '}
                <strong>{rejectTarget.consumer_email ?? `Споживач #${rejectTarget.consumer_id}`}</strong>{' '}
                на набір <strong>«{rejectTarget.dataset_name ?? rejectTarget.dataset_id}»</strong>:
              </p>

              <div className="form-group" style={{ marginTop: 'var(--space-3)' }}>
                <label htmlFor="reject-comment" className="form-label">
                  Причина відхилення <span className="required">*</span>
                </label>
                <textarea
                  id="reject-comment"
                  className="form-textarea"
                  rows={3}
                  placeholder="Вкажіть причину відхилення для споживача..."
                  value={rejectComment}
                  onChange={(e) => setRejectComment(e.target.value)}
                  disabled={rejectSubmitting}
                />
              </div>

              {rejectError && (
                <div className="alert-banner alert-banner--danger" style={{ marginTop: 'var(--space-3)' }}>
                  <IconAlert size={16} />
                  <div>{rejectError}</div>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <Button variant="secondary" onClick={() => setRejectTarget(null)} disabled={rejectSubmitting}>
                Скасувати
              </Button>
              <Button
                variant="primary"
                onClick={handleReject}
                disabled={rejectSubmitting}
                style={{ background: 'var(--color-danger)' }}
              >
                {rejectSubmitting ? 'Відхилення...' : 'Відхилити запит'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Модальне вікно відкликання згоди (UC-12) */}
      {showRevokeModal && (
        <div className="modal-backdrop" onClick={() => !consentRevoking && setShowRevokeModal(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="modal-header">
              <h3 className="modal-title">Відкликання згоди субʼєкта даних</h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setShowRevokeModal(false)}
                disabled={consentRevoking}
                aria-label="Закрити"
              >
                <IconX size={18} />
              </button>
            </div>

            <div className="modal-body">
              <div className="alert-banner alert-banner--warning">
                <IconAlert size={18} />
                <div>
                  <strong>Увага:</strong> Відкликання згоди є безповоротним процесом (UC-12). Після відкликання:
                  <ul style={{ margin: 'var(--space-1) 0 0 var(--space-4)' }}>
                    <li>Нові запити на доступ до набору не зможуть бути схвалені (409 Conflict).</li>
                    <li>Споживачі зі схваленими запитами втратять можливість завантажувати файл (403 Forbidden).</li>
                  </ul>
                </div>
              </div>

              <div className="form-group" style={{ marginTop: 'var(--space-4)' }}>
                <label htmlFor="revoke-reason" className="form-label">
                  Причина відкликання згоди (необовʼязково)
                </label>
                <textarea
                  id="revoke-reason"
                  className="form-textarea"
                  rows={2}
                  placeholder="Наприклад: Заява суб'єкта даних від 22.11.2026 про відкликання згоди на обробку"
                  value={revokeReason}
                  onChange={(e) => setRevokeReason(e.target.value)}
                  disabled={consentRevoking}
                />
              </div>
            </div>

            <div className="modal-footer">
              <Button variant="secondary" onClick={() => setShowRevokeModal(false)} disabled={consentRevoking}>
                Скасувати
              </Button>
              <Button
                variant="primary"
                onClick={handleRevokeConsent}
                disabled={consentRevoking}
                style={{ background: 'var(--color-danger)' }}
              >
                {consentRevoking ? 'Відкликання...' : 'Підтвердити відкликання згоди'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
