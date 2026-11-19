import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { fetchDatasets } from '../api/datasets'
import {
  checkPublication,
  fetchDatasetVersions,
  publishDataset,
} from '../api/publication'
import type {
  DatasetVersion,
  DatasetVersionInfo,
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
  IconInfo,
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

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('uk-UA')
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) {
      return 'Немає доступу. Лише власник набору з роллю Data Provider може публікувати набір.'
    }
    if (err.status === 404) {
      return 'Набір даних не знайдено або він не належить поточному користувачу.'
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
  const [versions, setVersions] = useState<DatasetVersionInfo[]>([])
  const [retentionUntil, setRetentionUntil] = useState<string>(getDefaultRetentionDate())
  const [gate, setGate] = useState<PublicationCheck | null>(null)
  const [publishedResult, setPublishedResult] = useState<PublishResult | null>(null)

  const [loading, setLoading] = useState(true)
  const [evaluatingGate, setEvaluatingGate] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // Завантаження базових даних про набір і версії
  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [allDatasets, vers] = await Promise.all([
        fetchDatasets(),
        fetchDatasetVersions(datasetId),
      ])
      const found = allDatasets.find((d) => String(d.id) === String(datasetId))
      if (found) {
        setDataset(found)
      }
      setVersions(vers)
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
      // Якщо перевірка повертає помилку
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

  const hasCleanVersion = useMemo(() => {
    return versions.some((v) => v.kind === 'clean')
  }, [versions])

  const cleanVersion = useMemo(() => {
    return versions.find((v) => v.kind === 'clean')
  }, [versions])

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
      // Оновлюємо статус набору локально
      if (dataset) {
        setDataset({
          ...dataset,
          status: 'Published',
          data_class: result.data_class,
        })
      }
    } catch (err) {
      setError(formatError(err))
      // Якщо 422, повторно запитуємо стан воріт
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
          <div className="pii-breadcrumbs">
            <Link to="/datasets" className="pii-breadcrumbs__link">
              <IconArrowLeft size={14} />
              <span>Список наборів</span>
            </Link>
            <span className="pii-breadcrumbs__sep">/</span>
            <Link to={`/datasets/${datasetId}`} className="pii-breadcrumbs__link">
              <span>{dataset?.dataset_name ?? `Набір #${datasetId}`}</span>
            </Link>
            <span className="pii-breadcrumbs__sep">/</span>
            <span className="pii-breadcrumbs__current">Публікація набору</span>
          </div>

          <div className="pii-title-row">
            <h1>Публікація: {dataset?.dataset_name ?? `Набір #${datasetId}`}</h1>
            {dataset && <StatusBadge value={dataset.status} />}
            {dataset && <ClassBadge value={dataset.data_class} />}
          </div>
          <p className="subtitle">
            Публікація набору даних у каталог з перевіркою правових підстав та воріт безпеки (UC-07).
          </p>
        </div>

        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <Button
            variant="secondary"
            onClick={() => {
              loadData()
              runGateCheck()
            }}
            disabled={loading || publishing}
          >
            <IconRefresh size={16} />
            <span>Оновити</span>
          </Button>
        </div>
      </div>

      {/* Повідомлення про помилку */}
      {error && (
        <ErrorMessage title="Помилка публікації">{error}</ErrorMessage>
      )}

      {/* Інформаційне повідомлення */}
      {notice && (
        <div className="alert alert--info">
          <IconInfo size={16} />
          <div className="alert__body">
            <span className="alert__title">Статус</span>
            <span>{notice}</span>
          </div>
        </div>
      )}

      {/* Успішна публікація (Banner) */}
      {(publishedResult || dataset?.status === 'Published') && (
        <div className="card published-success-card" style={{ border: '2px solid var(--color-success)', background: 'var(--success-bg)', padding: 'var(--space-6)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
            <IconCheckCircle size={32} style={{ color: 'var(--color-success)' }} />
            <div>
              <h2 style={{ margin: 0, color: 'var(--success-text)', fontSize: '20px' }}>Набір успішно опубліковано!</h2>
              <p style={{ margin: 0, color: 'var(--success-text)', fontSize: '14px' }}>
                Набір доступний у Каталозі для Data Consumer відповідно до встановленого класу доступу.
              </p>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-3)', padding: 'var(--space-3)', background: 'var(--color-white)', borderRadius: 'var(--radius-md)', margin: 'var(--space-4) 0' }}>
            <div>
              <span className="caption cell-muted">Клас набору:</span>
              <div>
                <ClassBadge value={publishedResult?.data_class ?? dataset?.data_class ?? 'Internal'} />
              </div>
            </div>
            <div>
              <span className="caption cell-muted">Зберігати до (Retention):</span>
              <div className="cell-strong">
                {formatDate(publishedResult?.retention_until ?? retentionUntil)}
              </div>
            </div>
            <div>
              <span className="caption cell-muted">Дата публікації:</span>
              <div className="cell-strong">
                {formatDateTime(publishedResult?.published_at ?? new Date().toISOString())}
              </div>
            </div>
            <div>
              <span className="caption cell-muted">Опублікував:</span>
              <div className="cell-strong">
                {publishedResult?.published_by ?? 'provider@example.com'}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
            <Link to="/catalog" className="btn btn--primary">
              <span>Перейти до каталогу наборів</span>
            </Link>
            <Link to="/datasets" className="btn btn--secondary">
              <span>До списку моїх наборів</span>
            </Link>
          </div>
        </div>
      )}

      {/* Секція 1: Очищена версія та історія версій */}
      <section className="card" aria-labelledby="versions-title">
        <div className="page-header page-header--row">
          <div>
            <h2 id="versions-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <IconFile size={20} />
              <span>Версії набору (Dataset Versions)</span>
            </h2>
            <p className="subtitle">
              Для публікації обов'язково потрібна знеособлена копія набору (`kind=clean`).
            </p>
          </div>

          {!hasCleanVersion && (
            <Link to={`/datasets/${datasetId}/anonymize`} className="btn btn--primary">
              <IconShield size={16} />
              <span>Створити очищену версію</span>
            </Link>
          )}
        </div>

        {!hasCleanVersion && (
          <div className="alert alert--warning" style={{ marginBottom: 'var(--space-4)' }}>
            <IconAlert size={16} />
            <div className="alert__body">
              <span className="alert__title">Відсутня очищена версія</span>
              <span>
                У цьому наборі ще немає знеособленої версії. Ворота публікації не пропустять сирий файл безпосередньо в каталог. Будь ласка, виконайте анонімізацію.
              </span>
            </div>
          </div>
        )}

        {hasCleanVersion && cleanVersion && (
          <div className="alert alert--success" style={{ marginBottom: 'var(--space-4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <IconCheck size={16} />
              <div className="alert__body">
                <span className="alert__title">Очищену версію знайдено (v{cleanVersion.version_number})</span>
                <span>
                  Файл: <code>{cleanVersion.file_name}</code> · Рядків: {cleanVersion.row_count} · Розмір: {formatBytes(cleanVersion.file_size)}
                </span>
              </div>
            </div>
            <Link to={`/datasets/${datasetId}/anonymize`} className="btn btn--secondary btn--sm">
              Змінити параметри анонімізації
            </Link>
          </div>
        )}

        {versions.length > 0 ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Версія</th>
                  <th scope="col">Тип (kind)</th>
                  <th scope="col">Файл</th>
                  <th scope="col">Клас</th>
                  <th scope="col">Рядків</th>
                  <th scope="col">SHA-256</th>
                  <th scope="col">Створено</th>
                </tr>
              </thead>
              <tbody>
                {versions.map((v) => (
                  <tr key={v.id}>
                    <td className="cell-strong">v{v.version_number}</td>
                    <td>
                      <span className={`badge ${v.kind === 'clean' ? 'badge--published' : 'badge--uploaded'}`}>
                        {v.kind === 'clean' ? 'Очищена (clean)' : 'Сира (raw)'}
                      </span>
                    </td>
                    <td><code>{v.file_name}</code></td>
                    <td>{v.data_class ? <ClassBadge value={v.data_class} /> : '—'}</td>
                    <td>{v.row_count}</td>
                    <td className="col-name-mono" title={v.sha256} style={{ fontSize: '11px' }}>
                      {v.sha256.slice(0, 12)}…
                    </td>
                    <td className="cell-muted">{formatDateTime(v.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="cell-muted">Завантаження інформації про версії…</p>
        )}
      </section>

      {/* Секція 2: Правові підстави (Legal Basis Panel) */}
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

        <div style={{ maxWidth: '380px' }}>
          <label className="field-label" htmlFor="retention-input">
            <span className="field-label__text">Зберігати до дати (retention_until) *:</span>
            <input
              id="retention-input"
              type="date"
              className="filter-select"
              style={{ width: '100%', fontSize: '14px', padding: '8px 12px' }}
              min={getTomorrowDate()}
              value={retentionUntil}
              onChange={(e) => handleRetentionChange(e.target.value)}
              required
            />
          </label>
          <span className="caption cell-muted" style={{ display: 'block', marginTop: '6px' }}>
            Обов'язкове поле (вимога GDPR). Дата має бути не раніше ніж завтра.
          </span>
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
                      ? 'Очищену копію створено успішно.'
                      : (cleanErr?.message || 'Очищена версія відсутня. Спочатку виконайте знеособлення на сторінці анонімізації.')}
                  </div>
                </div>
              </div>
            )
          })()}

          {/* 2. Обробка всіх PII колонок */}
          {(() => {
            const piiErr = gate?.reasons.find((r) => r.code === 'pii_not_processed')
            const isOk = !piiErr
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
                      : (piiErr?.message
                          ? `${piiErr.message}${piiErr.columns ? `: ${piiErr.columns.join(', ')}` : ''}`
                          : `Знайдено необроблені PII-колонки: ${(piiErr?.columns ?? []).join(', ')}. Усі персональні дані мають бути знеособлені.`)}
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
                      : (hmacErr?.message
                          ? `${hmacErr.message}${hmacErr.legal_basis_reason ? ` (${hmacErr.legal_basis_reason})` : ''}`
                          : `Для колонок із HMAC (${hmacCols.join(', ')}) відсутня активна правова підстава! Зареєструйте згоду чи договір вище.`)}
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
                      : (retErr?.message || 'Вкажіть коректну дату зберігання у формі вище (дата не раніше ніж завтра).')}
                  </div>
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
