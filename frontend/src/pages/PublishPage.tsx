import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { fetchDatasets } from '../api/datasets'
import {
  checkPublication,
  publishDataset,
} from '../api/publication'
import type {
  DatasetVersion,
  PublicationCheck,
  PublishResult,
} from '../api/types'
import { ClassBadge, StatusBadge } from '../components/Badges'
import { Button } from '../components/Button'
import { ErrorMessage } from '../components/ErrorMessage'
import {
  IconAlert,
  IconArrowLeft,
  IconCheck,
  IconCheckCircle,
  IconFile,
  IconRefresh,
  IconShield,
  IconX,
} from '../components/icons'
import { LegalBasisPanel } from '../components/LegalBasisPanel'

// ─── Допоміжні функції дати ──────────────────────────────────────────────────

function getTomorrowDate(): string {
  const tomorrow = new Date(Date.now() + 86400000)
  return tomorrow.toISOString().slice(0, 10)
}

function getDefaultRetentionDate(): string {
  const oneYearLater = new Date()
  oneYearLater.setFullYear(oneYearLater.getFullYear() + 1)
  return oneYearLater.toISOString().slice(0, 10)
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('uk-UA')
}

function formatError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) {
      return 'Немає доступу. Лише власник набору з роллю Data Provider може публікувати набір.'
    }
    if (err.status === 404) {
      if (err.message && (err.message.toLowerCase().includes('dataset') || err.message.includes('не знайдено'))) {
        return 'Набір даних не знайдено або він не належить поточному користувачу.'
      }
      return 'Публікація ще недоступна на сервері.'
    }
    if (err.status === 405) {
      return 'Публікація ще недоступна на сервері.'
    }
    if (err.status === 409) {
      return 'Набір даних вже опубліковано.'
    }
    if (err.status === 422) {
      return `Ворота публікації відмовили: ${err.message}`
    }
    return err.message
  }
  if (err instanceof Error) return err.message
  return 'Невідома помилка під час публікації'
}

// ─── Головний компонент PublishPage ──────────────────────────────────────────

export default function PublishPage() {
  const { id } = useParams<{ id: string }>()
  const datasetId = id ?? '1'

  const [dataset, setDataset] = useState<DatasetVersion | null>(null)
  const [retentionUntil, setRetentionUntil] = useState<string>(getDefaultRetentionDate())
  const [gate, setGate] = useState<PublicationCheck | null>(null)
  const [publishedResult, setPublishedResult] = useState<PublishResult | null>(null)

  const [loading, setLoading] = useState(true)
  const [evaluatingGate, setEvaluatingGate] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // Завантаження базових даних про набір
  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const allDatasets = await fetchDatasets()
      const found = allDatasets.find((d) => String(d.id) === String(datasetId))
      if (found) {
        setDataset(found)
      } else {
        setError('Набір даних не знайдено або він не належить поточному користувачу.')
      }
    } catch (err) {
      setError(formatError(err))
    } finally {
      setLoading(false)
    }
  }, [datasetId])

  // Перевірка воріт публікації (Publication Gate)
  const runGateCheck = useCallback(async (dateToTest?: string) => {
    const targetDate = dateToTest ?? retentionUntil
    setEvaluatingGate(true)
    try {
      const check = await checkPublication(datasetId, targetDate)
      setGate(check)
    } catch (err) {
      setError(formatError(err))
    } finally {
      setEvaluatingGate(false)
    }
  }, [datasetId, retentionUntil])

  useEffect(() => {
    loadData()
  }, [loadData])

  useEffect(() => {
    runGateCheck()
  }, [runGateCheck])

  // Чи є створена clean-версія з відповіді воріт публікації
  const cleanVersionId = gate?.clean_version_id ?? null
  const hasCleanVersion = cleanVersionId !== null || (gate !== null && !gate.reasons.some((r) => r.code === 'no_clean_version'))

  // Зміна терміну зберігання
  const handleRetentionChange = (val: string) => {
    setRetentionUntil(val)
    runGateCheck(val)
  }

  // Публікація набору
  const handlePublish = async () => {
    if (!retentionUntil) return
    setPublishing(true)
    setError(null)
    setNotice(null)
    try {
      const result = await publishDataset(datasetId, retentionUntil)
      setPublishedResult(result)
      setGate(result.gate)
      setNotice(`Набір успішно опубліковано! Новий клас: ${result.data_class}.`)
      if (dataset) {
        setDataset({
          ...dataset,
          status: 'Published',
          data_class: result.data_class,
        })
      }
    } catch (err) {
      setError(formatError(err))
      runGateCheck()
    } finally {
      setPublishing(false)
    }
  }

  // Перевірка чи ворота дозволяють публікацію
  const canPublish = useMemo(() => {
    return Boolean(
      gate?.allowed &&
      retentionUntil.trim().length > 0 &&
      !publishing &&
      dataset?.status !== 'Published' &&
      !publishedResult,
    )
  }, [gate, retentionUntil, publishing, dataset, publishedResult])

  return (
    <div className="publish-page" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      {/* Навігація / Breadcrumbs */}
      <div className="page-header page-header--row">
        <div>
          <div className="profile-breadcrumbs">
            <Link to="/datasets" className="profile-breadcrumbs__link">
              <IconArrowLeft size={14} />
              <span>До списку наборів</span>
            </Link>
            <span className="profile-breadcrumbs__sep">/</span>
            <Link to={`/datasets/${datasetId}`} className="profile-breadcrumbs__link">
              {dataset?.dataset_name ?? dataset?.file_name ?? `Набір #${datasetId}`}
            </Link>
            <span className="profile-breadcrumbs__sep">/</span>
            <span>Публікація набору</span>
          </div>
          <h1 className="page-title">Публікація набору даних (UC-07)</h1>
          <p className="page-subtitle">
            Перевірка воріт публікації (Publication Gate), встановлення терміну зберігання та реєстрація правових підстав.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <Button
            variant="secondary"
            onClick={() => {
              loadData()
              runGateCheck()
            }}
            disabled={loading || evaluatingGate}
            title="Оновити дані та стан воріт"
          >
            <IconRefresh size={14} className={loading || evaluatingGate ? 'icon-spin' : ''} />
            <span>Оновити</span>
          </Button>
        </div>
      </div>

      {error && <ErrorMessage>{error}</ErrorMessage>}

      {notice && (
        <div className="alert alert--success">
          <IconCheck size={18} />
          <div className="alert__body">
            <span>{notice}</span>
          </div>
        </div>
      )}

      {/* Повідомлення про успішну публікацію */}
      {publishedResult && (
        <div className="card published-success-card" style={{ borderColor: 'var(--color-success)', background: 'var(--success-bg)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-success)', flexShrink: 0 }}>
              <IconCheckCircle size={32} />
            </div>
            <div style={{ flex: 1 }}>
              <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--success-text)', margin: 0 }}>
                Набір даних успішно опубліковано!
              </h2>
              <div style={{ fontSize: '14px', color: 'var(--success-text)', marginTop: '4px' }}>
                Статус оновлено на <strong>Опубліковано (Published)</strong>. Фінальний клас даних: <ClassBadge value={publishedResult.data_class} />. Набір доступний для споживачів у Каталозі.
              </div>
            </div>
            <Link to="/catalog" className="button button--primary" style={{ flexShrink: 0 }}>
              Перейти до Каталогу
            </Link>
          </div>
        </div>
      )}

      {/* Огляд набору даних */}
      {dataset && (
        <div className="card" style={{ padding: 'var(--space-4) var(--space-5)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <h2 style={{ fontSize: '18px', fontWeight: 600, margin: 0 }}>{dataset.dataset_name}</h2>
                <StatusBadge value={dataset.status} />
              </div>
              <div className="cell-muted" style={{ fontSize: '13px', marginTop: '4px' }}>
                Файл: <code>{dataset.file_name}</code> · Поточний клас: <ClassBadge value={dataset.data_class} />
              </div>
            </div>

            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              <Link to={`/datasets/${datasetId}`} className="button button--secondary button--sm">
                Профіль набору
              </Link>
              <Link to={`/datasets/${datasetId}/anonymize`} className="button button--secondary button--sm">
                Анонімізація
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Секція 1: Очищена версія даних (Clean Version з publish/check) */}
      <section className="card" aria-labelledby="versions-title">
        <div className="page-header page-header--row">
          <div>
            <h2 id="versions-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <IconFile size={20} />
              <span>Очищена версія даних (Clean Version)</span>
            </h2>
            <p className="subtitle">
              Статус знеособленої версії набору, яка передається до публікації в Каталог.
            </p>
          </div>
          <Link to={`/datasets/${datasetId}/anonymize`} className="button button--secondary button--sm">
            Параметри анонімізації
          </Link>
        </div>

        {cleanVersionId ? (
          <div
            className="alert-banner"
            style={{
              background: 'var(--success-bg)',
              color: 'var(--success-text)',
              borderColor: 'var(--color-success)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <IconCheck size={20} />
              <div>
                <strong>Очищену копію сформовано (Версія #{cleanVersionId})</strong>
                <div style={{ fontSize: '13px', marginTop: '2px' }}>
                  Знеособлену версію набору підготовлено. Вона готова для проходження воріт публікації.
                </div>
              </div>
            </div>
            <Link
              to={`/datasets/${datasetId}/anonymize`}
              className="button button--secondary button--sm"
              style={{ background: 'white' }}
            >
              Змінити параметри
            </Link>
          </div>
        ) : (
          <div
            className="alert-banner alert-banner--warning"
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <IconAlert size={20} />
              <div>
                <strong>Очищена версія ще не створена</strong>
                <div style={{ fontSize: '13px', marginTop: '2px' }}>
                  Для публікації набору в Каталог необхідно спочатку виконати знеособлення (маскування, HMAC тощо).
                </div>
              </div>
            </div>
            <Link to={`/datasets/${datasetId}/anonymize`} className="button button--primary button--sm">
              Перейти до анонімізації
            </Link>
          </div>
        )}
      </section>

      {/* Секція 2: Правові підстави (Legal Basis Panel з #44) */}
      <LegalBasisPanel
        datasetId={datasetId}
        onChanged={() => runGateCheck()}
      />

      {/* Секція 3: Термін зберігання (Data Retention) */}
      <section className="card" aria-labelledby="retention-title">
        <div className="page-header">
          <h2 id="retention-title">Термін зберігання даних (Retention Period)</h2>
          <p className="subtitle">
            Встановіть дату, до якої набір даних зберігається та доступний в системі. Після настання цієї дати набір автоматично переходить у статус Expired.
          </p>
        </div>

        <div style={{ maxWidth: '420px', marginTop: 'var(--space-4)' }}>
          <label htmlFor="retention-input" className="form-label" style={{ fontWeight: 600 }}>
            Дата зберігання (Retention Until) <span className="required">*</span>
          </label>
          <input
            id="retention-input"
            type="date"
            className="form-input"
            value={retentionUntil}
            min={getTomorrowDate()}
            onChange={(e) => handleRetentionChange(e.target.value)}
            disabled={publishing || dataset?.status === 'Published'}
            style={{ marginTop: 'var(--space-1)' }}
          />
          <div className="cell-muted" style={{ fontSize: '12px', marginTop: '6px' }}>
            Вкажіть майбутню дату (не раніше ніж завтра). За замовчуванням встановлено 1 рік.
          </div>
        </div>
      </section>

      {/* Секція 4: Перевірка воріт публікації (Publication Gate Checklist) */}
      <section className="card gate-section" aria-labelledby="gate-title" style={{ borderColor: gate?.allowed ? 'var(--color-success)' : 'var(--color-line)' }}>
        <div className="page-header page-header--row">
          <div>
            <h2 id="gate-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <IconShield size={20} />
              <span>Ворота публікації (Publication Gate)</span>
            </h2>
            <p className="subtitle">
              Автоматична перевірка безпеки та відповідності перед публікацією набору (read-only перевірка).
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="caption cell-muted">Очікуваний клас:</span>
            {gate && <ClassBadge value={gate.new_class} />}
          </div>
        </div>

        {evaluatingGate && (
          <div className="alert alert--info" style={{ marginBottom: 'var(--space-4)' }}>
            <IconRefresh size={16} />
            <div className="alert__body">
              <span>Оцінка умов публікації…</span>
            </div>
          </div>
        )}

        {/* Чек-лист критеріїв воріт */}
        <div className="gate-checklist" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', margin: 'var(--space-4) 0' }}>
          {/* 1. Наявність очищеної версії */}
          {(() => {
            const cleanErr = gate?.reasons.find((r) => r.code === 'no_clean_version')
            const isOk = !cleanErr && hasCleanVersion
            return (
              <div className={`gate-item ${isOk ? 'gate-item--ok' : 'gate-item--fail'}`} style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', padding: '12px', borderRadius: 'var(--radius-sm)', background: isOk ? 'var(--success-bg)' : 'var(--danger-soft)' }}>
                {isOk ? (
                  <IconCheck size={20} style={{ color: 'var(--color-success)', flexShrink: 0, marginTop: '2px' }} />
                ) : (
                  <IconX size={20} style={{ color: 'var(--color-danger)', flexShrink: 0, marginTop: '2px' }} />
                )}
                <div>
                  <div className="cell-strong" style={{ color: isOk ? 'var(--success-text)' : 'var(--danger-text)' }}>
                    Наявність очищеної версії набору
                  </div>
                  <div style={{ fontSize: '13px', color: isOk ? 'var(--success-text)' : 'var(--danger-text)' }}>
                    {isOk
                      ? `Очищену копію створено успішно${cleanVersionId ? ` (ID: #${cleanVersionId})` : ''}.`
                      : 'Очищена версія відсутня. Спочатку виконайте знеособлення на сторінці анонімізації.'}
                  </div>
                </div>
              </div>
            )
          })()}

          {/* 2. Обробка всіх PII колонок */}
          {(() => {
            const piiErr = gate?.reasons.find((r) => r.code === 'pii_not_processed')
            const isOk = !piiErr
            const missing = piiErr?.columns ?? gate?.missing_columns ?? []
            return (
              <div className={`gate-item ${isOk ? 'gate-item--ok' : 'gate-item--fail'}`} style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', padding: '12px', borderRadius: 'var(--radius-sm)', background: isOk ? 'var(--success-bg)' : 'var(--danger-soft)' }}>
                {isOk ? (
                  <IconCheck size={20} style={{ color: 'var(--color-success)', flexShrink: 0, marginTop: '2px' }} />
                ) : (
                  <IconX size={20} style={{ color: 'var(--color-danger)', flexShrink: 0, marginTop: '2px' }} />
                )}
                <div>
                  <div className="cell-strong" style={{ color: isOk ? 'var(--success-text)' : 'var(--danger-text)' }}>
                    Обробка виявлених PII-колонок
                  </div>
                  <div style={{ fontSize: '13px', color: isOk ? 'var(--success-text)' : 'var(--danger-text)' }}>
                    {isOk
                      ? 'Усі PII-колонки оброблено обраними методами.'
                      : `Знайдено необроблені PII-колонки${missing.length > 0 ? `: ${missing.join(', ')}` : ''}. Усі персональні дані мають бути знеособлені.`}
                  </div>
                </div>
              </div>
            )
          })()}

          {/* 3. Правова підстава для HMAC */}
          {(() => {
            const hmacErr = gate?.reasons.find((r) => r.code === 'hmac_without_legal_basis')
            const isOk = !hmacErr
            const hmacCols = gate?.hmac_columns ?? []
            return (
              <div className={`gate-item ${isOk ? 'gate-item--ok' : 'gate-item--fail'}`} style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', padding: '12px', borderRadius: 'var(--radius-sm)', background: isOk ? 'var(--success-bg)' : 'var(--danger-soft)' }}>
                {isOk ? (
                  <IconCheck size={20} style={{ color: 'var(--color-success)', flexShrink: 0, marginTop: '2px' }} />
                ) : (
                  <IconX size={20} style={{ color: 'var(--color-danger)', flexShrink: 0, marginTop: '2px' }} />
                )}
                <div>
                  <div className="cell-strong" style={{ color: isOk ? 'var(--success-text)' : 'var(--danger-text)' }}>
                    Правова підстава для HMAC (псевдонімізація)
                  </div>
                  <div style={{ fontSize: '13px', color: isOk ? 'var(--success-text)' : 'var(--danger-text)' }}>
                    {isOk
                      ? hmacCols.length > 0
                        ? `Для колонок із HMAC (${hmacCols.join(', ')}) зареєстровано активну правову підставу.`
                        : 'HMAC-псевдонімізація не використовується (або зареєстровано чинну підставу).'
                      : `Для колонок із HMAC (${hmacCols.join(', ')}) відсутня активна правова підстава! Зареєструйте згоду чи договір вище.`}
                  </div>
                  <div className="cell-muted" style={{ fontSize: '12px', marginTop: '4px' }}>
                    Для HMAC потрібна чинна правова підстава. Без неї запити можна створити, але власник не зможе їх схвалити.
                  </div>
                </div>
              </div>
            )
          })()}

          {/* 4. Термін зберігання */}
          {(() => {
            const retErr = gate?.reasons.find((r) => r.code === 'retention_required')
            const isOk = !retErr && retentionUntil.trim().length > 0
            return (
              <div className={`gate-item ${isOk ? 'gate-item--ok' : 'gate-item--fail'}`} style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', padding: '12px', borderRadius: 'var(--radius-sm)', background: isOk ? 'var(--success-bg)' : 'var(--danger-soft)' }}>
                {isOk ? (
                  <IconCheck size={20} style={{ color: 'var(--color-success)', flexShrink: 0, marginTop: '2px' }} />
                ) : (
                  <IconX size={20} style={{ color: 'var(--color-danger)', flexShrink: 0, marginTop: '2px' }} />
                )}
                <div>
                  <div className="cell-strong" style={{ color: isOk ? 'var(--success-text)' : 'var(--danger-text)' }}>
                    Термін зберігання (Retention Until)
                  </div>
                  <div style={{ fontSize: '13px', color: isOk ? 'var(--success-text)' : 'var(--danger-text)' }}>
                    {isOk
                      ? `Встановлено термін зберігання: ${formatDate(retentionUntil)}.`
                      : 'Вкажіть коректну дату зберігання у формі вище (дата не раніше ніж завтра).'}
                  </div>
                </div>
              </div>
            )
          })()}

          {/* 5. Перевірка правил якості даних (SCRUM-57 quality_blocked) */}
          {(() => {
            const qualityErr = gate?.reasons.find((r) => r.code === 'quality_blocked')
            const isOk = !qualityErr
            return (
              <div className={`gate-item ${isOk ? 'gate-item--ok' : 'gate-item--fail'}`} style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', padding: '12px', borderRadius: 'var(--radius-sm)', background: isOk ? 'var(--success-bg)' : 'var(--danger-soft)' }}>
                {isOk ? (
                  <IconCheck size={20} style={{ color: 'var(--color-success)', flexShrink: 0, marginTop: '2px' }} />
                ) : (
                  <IconX size={20} style={{ color: 'var(--color-danger)', flexShrink: 0, marginTop: '2px' }} />
                )}
                <div style={{ flex: 1 }}>
                  <div className="cell-strong" style={{ color: isOk ? 'var(--success-text)' : 'var(--danger-text)' }}>
                    Перевірка правил якості (Quality Rules)
                  </div>
                  <div style={{ fontSize: '13px', color: isOk ? 'var(--success-text)' : 'var(--danger-text)' }}>
                    {isOk
                      ? 'Критичних блокуючих порушень правил якості даних не виявлено.'
                      : 'Публікацію заблоковано через невиконання критичних правил якості даних.'}
                  </div>
                  {!isOk && (
                    <div style={{ marginTop: 'var(--space-2)' }}>
                      <Link to={`/datasets/${datasetId}/quality`} className="button button--secondary button--sm">
                        Переглянути правила якості
                      </Link>
                    </div>
                  )}
                </div>
              </div>
            )
          })()}
        </div>

        {/* Підсумковий вердикт воріт */}
        {gate && (
          <div style={{ marginTop: 'var(--space-4)', padding: 'var(--space-4)', borderRadius: 'var(--radius-md)', background: gate.allowed ? 'var(--success-bg)' : 'var(--warning-bg)', border: `1px solid ${gate.allowed ? 'var(--color-success)' : 'var(--color-warning)'}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {gate.allowed ? (
                <IconCheckCircle size={20} style={{ color: 'var(--color-success)' }} />
              ) : (
                <IconAlert size={20} style={{ color: 'var(--color-warning)' }} />
              )}
              <span style={{ fontWeight: 600, color: gate.allowed ? 'var(--success-text)' : 'var(--warning-text)' }}>
                {gate.allowed
                  ? 'Усі критерії воріт виконано. Набір готовий до публікації!'
                  : 'Публікацію заблоковано воротами безпеки. Усуньте вказані зауваження для публікації.'}
              </span>
            </div>
          </div>
        )}

        {/* Кнопка дії публікації */}
        <div className="card__footer" style={{ marginTop: 'var(--space-4)', display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-3)' }}>
          <Button
            variant="secondary"
            onClick={() => runGateCheck()}
            disabled={evaluatingGate || publishing}
          >
            Повторити перевірку воріт
          </Button>
          <Button
            variant="primary"
            onClick={handlePublish}
            disabled={!canPublish}
          >
            {publishing ? 'Публікація…' : 'Опублікувати набір даних'}
          </Button>
        </div>
      </section>
    </div>
  )
}
