import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { createExchangeRequest, fetchCatalog } from '../api/exchange'
import {
  LEGAL_BASIS_PURPOSE_LABELS,
  type CatalogItem,
  type DataClass,
  type LegalBasisPurpose,
} from '../api/types'
import { useAuth } from '../auth/useAuth'
import { ClassBadge } from '../components/Badges'
import { Button } from '../components/Button'
import { ErrorMessage } from '../components/ErrorMessage'
import {
  IconAlert,
  IconCheck,
  IconDatabase,
  IconRefresh,
  IconSearch,
  IconShield,
  IconX,
} from '../components/icons'

const PURPOSES: LegalBasisPurpose[] = ['analytics', 'research', 'reporting', 'publication']

export default function CatalogPage() {
  const { role } = useAuth()
  const isConsumer = role === 'DataConsumer'
  const isSteward = role === 'DataSteward'

  const [items, setItems] = useState<CatalogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [search, setSearch] = useState('')
  const [selectedClass, setSelectedClass] = useState<string>('all')

  // Request Access Modal State
  const [selectedDataset, setSelectedDataset] = useState<CatalogItem | null>(null)
  const [selectedPurpose, setSelectedPurpose] = useState<LegalBasisPurpose>('analytics')
  const [purposeDetails, setPurposeDetails] = useState('')
  const [requestSubmitting, setRequestSubmitting] = useState(false)
  const [requestError, setRequestError] = useState<string | null>(null)
  const [requestSuccess, setRequestSuccess] = useState<string | null>(null)

  const loadCatalog = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchCatalog()
      setItems(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося завантажити каталог')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadCatalog()
  }, [loadCatalog])

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      if (search.trim()) {
        const q = search.toLowerCase()
        const matchesName = item.name.toLowerCase().includes(q)
        const matchesOwner = item.uploaded_by.toLowerCase().includes(q)
        if (!matchesName && !matchesOwner) return false
      }
      if (selectedClass !== 'all' && item.data_class !== selectedClass) {
        return false
      }
      return true
    })
  }, [items, search, selectedClass])

  const openRequestModal = (item: CatalogItem) => {
    setSelectedDataset(item)
    setSelectedPurpose('analytics')
    setPurposeDetails('')
    setRequestError(null)
    setRequestSuccess(null)
  }

  const closeRequestModal = () => {
    if (requestSubmitting) return
    setSelectedDataset(null)
    setPurposeDetails('')
    setRequestError(null)
    setRequestSuccess(null)
  }

  const handleSendRequest = async () => {
    if (!selectedDataset) return
    setRequestSubmitting(true)
    setRequestError(null)
    try {
      // Backend вимагає purpose min_length=10 і відповідність категорії
      const finalPurpose = purposeDetails.trim()
        ? `${selectedPurpose}: ${purposeDetails.trim()}`
        : `Цільове використання: ${selectedPurpose} (обробка згідно з регламентом)`
      await createExchangeRequest(selectedDataset.id, finalPurpose)
      setRequestSuccess(`Запит на доступ до набору «${selectedDataset.name}» успішно надіслано!`)
    } catch (err) {
      setRequestError(err instanceof Error ? err.message : 'Не вдалося надіслати запит на доступ')
    } finally {
      setRequestSubmitting(false)
    }
  }

  return (
    <div className="catalog-page">
      <div className="page-header page-header--row">
        <div>
          <h1 className="page-title">
            {isSteward ? 'Каталог даних (метадані)' : 'Каталог наборів даних'}
          </h1>
          <p className="page-subtitle">
            {isSteward
              ? 'Моніторинг опублікованих наборів даних, їх класів чутливості та параметрів анонімізації'
              : 'Опубліковані набори даних, готові до обміну відповідно до правил доступу'}
          </p>
        </div>
        <Button variant="secondary" onClick={loadCatalog} disabled={loading} title="Оновити список">
          <IconRefresh size={14} className={loading ? 'icon-spin' : ''} />
          <span>Оновити</span>
        </Button>
      </div>

      {/* Фільтри та пошук */}
      <div className="table-toolbar" style={{ marginTop: 'var(--space-4)' }}>
        <div className="table-toolbar__search">
          <IconSearch size={16} />
          <input
            type="search"
            placeholder="Пошук за назвою набору чи власником..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Пошук наборів"
          />
        </div>

        <div className="table-toolbar__filters">
          <div className="select-wrapper">
            <select
              value={selectedClass}
              onChange={(e) => setSelectedClass(e.target.value)}
              aria-label="Фільтр за класом даних"
            >
              <option value="all">Усі класи даних</option>
              <option value="Public">Public (Відкриті)</option>
              <option value="Internal">Internal (Внутрішні)</option>
              <option value="Confidential">Confidential (Конфіденційні)</option>
              <option value="Personal">Personal (Персональні)</option>
            </select>
          </div>
        </div>
      </div>

      {error && (
        <div style={{ marginTop: 'var(--space-4)' }}>
          <ErrorMessage title="Помилка завантаження каталогу">{error}</ErrorMessage>
        </div>
      )}

      {loading && items.length === 0 ? (
        <div className="empty" style={{ minHeight: '260px' }}>
          <p>Завантаження каталогу наборів даних...</p>
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="empty" style={{ minHeight: '260px' }}>
          <IconDatabase size={40} style={{ opacity: 0.4, marginBottom: 'var(--space-2)' }} />
          <h3>Опублікованих наборів не знайдено</h3>
          <p>
            {items.length === 0
              ? 'Наразі в каталозі немає жодного опублікованого набору.'
              : 'За заданими критеріями пошуку або фільтрами результатів немає.'}
          </p>
        </div>
      ) : (
        <div className="catalog-grid" style={{ marginTop: 'var(--space-5)' }}>
          {filteredItems.map((item) => (
            <div key={item.id} className="card catalog-card">
              <div className="catalog-card__header">
                <div>
                  <h3 className="catalog-card__title">{item.name}</h3>
                  <span className="caption">Власник: {item.uploaded_by}</span>
                </div>
                <ClassBadge value={item.data_class as DataClass} />
              </div>

              <div className="catalog-card__meta">
                <div className="catalog-meta-item">
                  <span className="caption">Кількість рядків</span>
                  <strong>{item.row_count.toLocaleString('uk-UA')}</strong>
                </div>
                <div className="catalog-meta-item">
                  <span className="caption">Quality Score</span>
                  <strong
                    style={{
                      color:
                        item.quality_score !== null && item.quality_score >= 80
                          ? 'var(--color-success)'
                          : item.quality_score !== null && item.quality_score >= 50
                          ? 'var(--color-warning)'
                          : item.quality_score !== null
                          ? 'var(--color-danger)'
                          : undefined,
                    }}
                  >
                    {item.quality_score !== null ? `${Math.round(item.quality_score)}%` : '—'}
                  </strong>
                </div>
              </div>

              {item.anonymization_methods && item.anonymization_methods.length > 0 && (
                <div className="catalog-card__anonymization">
                  <span className="caption" style={{ display: 'block', marginBottom: 'var(--space-1)' }}>
                    Методи анонімізації:
                  </span>
                  <div className="anonym-tags">
                    {item.anonymization_methods.map((m, idx) => (
                      <span key={idx} className="anonym-tag">
                        <code>{m.column}</code>: {m.method}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="catalog-card__footer">
                {isConsumer && (
                  <Button
                    variant="primary"
                    onClick={() => openRequestModal(item)}
                    style={{ width: '100%' }}
                  >
                    Запросити доступ
                  </Button>
                )}
                {isSteward && (
                  <div className="steward-badge-note">
                    <IconShield size={14} />
                    <span>Перегляд метаданих Data Steward</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Модальне вікно запиту на доступ (UC-08) */}
      {selectedDataset && (
        <div className="modal-backdrop" onClick={closeRequestModal}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="modal-header">
              <h3 className="modal-title">Запит на доступ до набору</h3>
              <button
                type="button"
                className="modal-close"
                onClick={closeRequestModal}
                disabled={requestSubmitting}
                aria-label="Закрити"
              >
                <IconX size={18} />
              </button>
            </div>

            <div className="modal-body">
              {requestSuccess ? (
                <div className="modal-success-state">
                  <div className="success-icon-wrap">
                    <IconCheck size={32} />
                  </div>
                  <h4>Запит успішно надіслано!</h4>
                  <p>{requestSuccess}</p>
                  <p className="caption" style={{ marginTop: 'var(--space-2)' }}>
                    Власник або Data Steward розгляне ваш запит. Після схвалення ви зможете завантажити очищений набір у розділі «Мої запити».
                  </p>
                </div>
              ) : (
                <>
                  <div className="modal-dataset-preview">
                    <div>
                      <div className="modal-dataset-name">{selectedDataset.name}</div>
                      <div className="caption">
                        {selectedDataset.row_count.toLocaleString('uk-UA')} рядків · Власник: {selectedDataset.uploaded_by}
                      </div>
                    </div>
                    <ClassBadge value={selectedDataset.data_class as DataClass} />
                  </div>

                  <div className="form-group" style={{ marginTop: 'var(--space-4)' }}>
                    <label htmlFor="request-purpose" className="form-label">
                      Мета використання даних <span className="required">*</span>
                    </label>
                    <select
                      id="request-purpose"
                      className="form-select"
                      value={selectedPurpose}
                      onChange={(e) => setSelectedPurpose(e.target.value as LegalBasisPurpose)}
                      disabled={requestSubmitting}
                    >
                      {PURPOSES.map((p) => (
                        <option key={p} value={p}>
                          {LEGAL_BASIS_PURPOSE_LABELS[p]}
                        </option>
                      ))}
                    </select>
                    <p className="form-hint">
                      Вкажіть категорію мети використання даних відповідно до вимог комплаєнсу та GDPR.
                    </p>
                  </div>

                  <div className="form-group" style={{ marginTop: 'var(--space-3)' }}>
                    <label htmlFor="request-details" className="form-label">
                      Деталізація мети / обґрунтування (необовʼязково)
                    </label>
                    <textarea
                      id="request-details"
                      className="form-textarea"
                      rows={2}
                      placeholder="Наприклад: Аналіз клієнтських сегментів для підготовки звіту за Q4"
                      value={purposeDetails}
                      onChange={(e) => setPurposeDetails(e.target.value)}
                      disabled={requestSubmitting}
                    />
                  </div>

                  <div className="compliance-notice" style={{ marginTop: 'var(--space-4)' }}>
                    <IconAlert size={16} />
                    <div>
                      <strong>Зверніть увагу:</strong> Запит буде перевірено Data Steward. Доступ надається лише за наявності чинної правової підстави для обраної мети.
                    </div>
                  </div>

                  {requestError && (
                    <div className="form-error" style={{ marginTop: 'var(--space-3)' }}>
                      <IconAlert size={14} />
                      <span>{requestError}</span>
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="modal-footer">
              {requestSuccess ? (
                <>
                  <Link to="/requests" className="button button--primary" onClick={closeRequestModal}>
                    Перейти до «Мої запити»
                  </Link>
                  <Button variant="secondary" onClick={closeRequestModal}>
                    Закрити
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="secondary" onClick={closeRequestModal} disabled={requestSubmitting}>
                    Скасувати
                  </Button>
                  <Button variant="primary" onClick={handleSendRequest} disabled={requestSubmitting}>
                    {requestSubmitting ? 'Надсилання...' : 'Надіслати запит'}
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
