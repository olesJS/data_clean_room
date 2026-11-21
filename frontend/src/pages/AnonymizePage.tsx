import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { applyAnonymization, previewAnonymization } from '../api/anonymization'
import { ApiError } from '../api/client'
import { fetchPiiScan } from '../api/datasets'
import type {
  AnonymizationMethodName,
  AnonymizationPreview,
  AnonymizedVersion,
  PiiFinding,
  PiiScanResponse,
  PiiType,
} from '../api/types'
import { ANONYMIZATION_METHOD_LABELS } from '../api/types'
import { ClassBadge } from '../components/Badges'
import { Button } from '../components/Button'
import { ErrorMessage } from '../components/ErrorMessage'
import {
  IconAlert,
  IconArrowLeft,
  IconArrowRight,
  IconCheckCircle,
  IconInfo,
  IconRefresh,
  IconShield,
} from '../components/icons'

// ─── Константи та мітки ────────────────────────────────────────────────────────

const PII_TYPE_LABELS: Record<Exclude<PiiType, null>, string> = {
  person_name: "ПІБ / Ім'я",
  ipn: 'ІПН (РНОКПП)',
  passport: 'Паспорт',
  iban: 'IBAN',
  card: 'Банківська картка',
  email: 'Електронна пошта',
  phone: 'Телефон',
  address: 'Адреса',
  birth_date: 'Дата народження',
}

const DEFAULT_METHODS_BY_TYPE: Record<string, AnonymizationMethodName> = {
  person_name: 'mask',
  address: 'mask',
  email: 'mask',
  phone: 'mask',
  birth_date: 'generalize',
  ipn: 'mask',
  passport: 'mask',
  iban: 'mask',
  card: 'mask',
}

function getDefaultMethod(piiType?: string | null): AnonymizationMethodName {
  if (!piiType) return 'mask'
  return DEFAULT_METHODS_BY_TYPE[piiType.toLowerCase()] ?? 'mask'
}

function PiiTypeBadge({ type }: { type: PiiType }) {
  if (!type) return <span className="cell-muted">—</span>
  const label = PII_TYPE_LABELS[type] ?? type
  return (
    <span className="badge badge--pii-type" title={`PII тип: ${type}`}>
      <IconShield size={12} />
      {label}
    </span>
  )
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const level = pct >= 90 ? 'high' : pct >= 70 ? 'medium' : 'low'
  return (
    <div className="confidence-cell">
      <span className={`confidence-pct confidence-pct--${level}`}>{pct}%</span>
      <div
        className="confidence-bar"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`confidence-bar__fill confidence-bar__fill--${level}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function formatError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) {
      return 'Немає доступу. Лише власник набору з роллю Data Provider може виконувати анонімізацію.'
    }
    if (err.status === 404) {
      return 'Набір даних не знайдено або він не належить поточному користувачу.'
    }
    if (err.status === 422) {
      return `Помилка параметрів анонімізації: ${err.message}`
    }
    return err.message
  }
  if (err instanceof Error) return err.message
  return 'Невідома помилка під час операції з набором'
}

// ─── Головний компонент ─────────────────────────────────────────────────────────

export default function AnonymizePage() {
  const { id } = useParams<{ id: string }>()
  const datasetId = id ?? '1'
  const navigate = useNavigate()

  const [scan, setScan] = useState<PiiScanResponse | null>(null)
  const [methods, setMethods] = useState<Record<string, AnonymizationMethodName>>({})
  const [preview, setPreview] = useState<AnonymizationPreview | null>(null)
  const [applied, setApplied] = useState<AnonymizedVersion | null>(null)

  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<'preview' | 'apply' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // Завантаження результатів сканування для набору
  const loadScanData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchPiiScan(datasetId)
      setScan(data)

      // Ініціалізуємо методи за замовчуванням
      const initial: Record<string, AnonymizationMethodName> = {}
      for (const f of data.findings) {
        const type = f.corrected_pii_type ?? f.pii_type
        initial[f.column_name] = getDefaultMethod(type)
      }
      setMethods(initial)
    } catch (err) {
      setError(formatError(err))
    } finally {
      setLoading(false)
    }
  }, [datasetId])

  useEffect(() => {
    loadScanData()
  }, [loadScanData])

  const findings: PiiFinding[] = useMemo(() => scan?.findings ?? [], [scan])

  const hasHmac = useMemo(() => {
    return Object.values(methods).includes('hmac')
  }, [methods])

  const unconfiguredCount = useMemo(() => {
    return findings.filter((f) => !methods[f.column_name]).length
  }, [findings, methods])

  const canApply = useMemo(() => {
    return (
      findings.length > 0 &&
      Object.keys(methods).length === findings.length &&
      unconfiguredCount === 0 &&
      busy === null
    )
  }, [findings.length, methods, unconfiguredCount, busy])

  // Зміна методу для конкретної колонки
  const handleMethodChange = (columnName: string, method: AnonymizationMethodName) => {
    if (method === 'redact') return
    setMethods((prev) => ({
      ...prev,
      [columnName]: method,
    }))
    // Скидаємо старий прев'ю якщо змінилися методи
    setPreview(null)
    setNotice(null)
  }

  // Запуск попереднього перегляду
  const handlePreview = async () => {
    setBusy('preview')
    setError(null)
    setNotice(null)
    try {
      const res = await previewAnonymization(datasetId, methods)
      setPreview(res)
      setNotice('Попередній перегляд успішно побудовано. Перегляньте значення у таблиці нижче.')
    } catch (err) {
      setError(formatError(err))
    } finally {
      setBusy(null)
    }
  }

  // Застосування анонімізації
  const handleApply = async () => {
    setBusy('apply')
    setError(null)
    setNotice(null)
    try {
      const res = await applyAnonymization(datasetId, methods)
      setApplied(res)
      setPreview(null)
      setNotice('Очищені дані збережено у clean-версії набору.')
      try {
        const freshScan = await fetchPiiScan(datasetId)
        setScan(freshScan)
      } catch {
        // Якщо повторний запит scan завершився з помилкою, не ламаємо стан успіху
      }
    } catch (err) {
      setError(formatError(err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="anonymize-page">
      {/* Навігаційні крихти та заголовок */}
      <div className="page-header page-header--row">
        <div>
          <div className="pii-breadcrumbs">
            <Link to="/datasets" className="pii-breadcrumbs__link">
              <IconArrowLeft size={14} />
              <span>Список наборів</span>
            </Link>
            <span className="pii-breadcrumbs__sep">/</span>
            <Link to={`/datasets/${datasetId}/pii`} className="pii-breadcrumbs__link">
              <span>PII сканування #{datasetId}</span>
            </Link>
            <span className="pii-breadcrumbs__sep">/</span>
            <span className="pii-breadcrumbs__current">Анонімізація даних</span>
          </div>

          <div className="pii-title-row">
            <h1>Анонімізація: {scan?.dataset_name ?? `Набір #${datasetId}`}</h1>
            {scan?.data_class && (
              <span className="badge badge--quality-medium" title="Поточний клас набору даних (з бекенду)">
                Клас набору: {scan.data_class}
              </span>
            )}
            {preview?.estimated_class && (
              <span className="badge badge--quality-medium" title="Очікуваний клас (відповідь API)">
                Очікуваний клас: {preview.estimated_class}
              </span>
            )}
          </div>
          <p className="subtitle">
            Вибір методів знеособлення для PII-колонок та перевірка результату «до/після» (UC-06).
          </p>
        </div>

        <div className="anonymize-header-actions">
          <Button
            variant="secondary"
            onClick={loadScanData}
            disabled={loading || busy !== null}
          >
            <IconRefresh size={16} />
            <span>Оновити</span>
          </Button>
        </div>
      </div>

      {/* Повідомлення про помилку */}
      {error && (
        <div style={{ marginBottom: 'var(--space-4)' }}>
          <ErrorMessage title="Помилка анонімізації">{error}</ErrorMessage>
        </div>
      )}

      {/* Інформаційне повідомлення */}
      {notice && (
        <div className="alert alert--info" style={{ marginBottom: 'var(--space-4)' }}>
          <IconInfo size={16} />
          <div className="alert__body">
            <span className="alert__title">Інформація</span>
            <span>{notice}</span>
          </div>
        </div>
      )}

      {/* Стан завантаження */}
      {loading ? (
        <div className="card loading-card">
          <div className="skeleton-row" style={{ width: '40%', height: '24px', marginBottom: '12px' }} />
          <div className="skeleton-row" style={{ width: '100%', height: '160px' }} />
        </div>
      ) : findings.length === 0 ? (
        /* Порожній стан */
        <div className="card empty-card" style={{ textAlign: 'center', padding: 'var(--space-8)' }}>
          <IconShield size={40} style={{ color: 'var(--color-neutral)', marginBottom: 'var(--space-3)' }} />
          <h2>PII не знайдено</h2>
          <p className="cell-muted" style={{ maxWidth: '480px', margin: '0 auto var(--space-4)' }}>
            У цьому наборі даних не виявлено персональних колонок. Анонімізація не потрібна — набір готовий до публікації.
          </p>
          <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'center' }}>
            <Link to={`/datasets/${datasetId}`} className="btn btn--secondary">
              До огляду набору
            </Link>
            <Link to="/datasets" className="btn btn--primary">
              До списку наборів
            </Link>
          </div>
        </div>
      ) : (
        <>
          {/* Успішне створення очищеної версії */}
          {applied && (
            <div className="card clean-version-card" style={{ marginBottom: 'var(--space-6)', borderColor: 'var(--color-success)' }}>
              <div className="clean-version-card__header" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
                <IconCheckCircle size={28} style={{ color: 'var(--color-success)' }} />
                <div>
                  <h3 style={{ margin: 0, fontSize: '18px' }}>Clean-версію успішно оновлено!</h3>
                  <p className="cell-muted" style={{ margin: 0, fontSize: '13px' }}>
                    Очищені дані збережено у clean-версії набору.
                  </p>
                </div>
              </div>

              <div className="clean-version-details" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 'var(--space-3)', padding: 'var(--space-3)', background: 'var(--color-light)', borderRadius: 'var(--radius-md)', marginBottom: 'var(--space-4)' }}>
                {applied.file_name && (
                  <div>
                    <span className="caption cell-muted">Файл версії:</span>
                    <div className="cell-strong">{applied.file_name}</div>
                  </div>
                )}
                {applied.version_number !== undefined && (
                  <div>
                    <span className="caption cell-muted">Номер версії:</span>
                    <div className="cell-strong">v{applied.version_number}</div>
                  </div>
                )}
                <div>
                  <span className="caption cell-muted">Кількість рядків:</span>
                  <div className="cell-strong">{applied.row_count}</div>
                </div>
                {applied.data_class ? (
                  <div>
                    <span className="caption cell-muted">Клас даних (з API):</span>
                    <div><ClassBadge value={applied.data_class} /></div>
                  </div>
                ) : scan?.data_class ? (
                  <div>
                    <span className="caption cell-muted">Клас набору (з API):</span>
                    <div><ClassBadge value={scan.data_class} /></div>
                  </div>
                ) : null}
                {applied.sha256 ? (
                  <div>
                    <span className="caption cell-muted">Контрольна сума SHA-256:</span>
                    <div className="col-name-mono" title={applied.sha256} style={{ fontSize: '12px' }}>
                      {applied.sha256.length > 16 ? `${applied.sha256.slice(0, 16)}…` : applied.sha256}
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="clean-version-actions" style={{ display: 'flex', gap: 'var(--space-3)' }}>
                <Button
                  variant="primary"
                  onClick={() => navigate(`/datasets/${datasetId}/publish`)}
                  title="Перейти до перевірки шлюзу та публікації набору (UC-07)"
                >
                  <span>Перейти до публікації</span>
                  <IconArrowRight size={16} />
                </Button>
                <Link to="/datasets" className="btn btn--secondary">
                  До списку наборів
                </Link>
              </div>
            </div>
          )}

          {/* Таблиця налаштування методів анонімізації для PII-колонок */}
          <section className="card" aria-labelledby="methods-config-title" style={{ marginBottom: 'var(--space-6)' }}>
            <div className="page-header">
              <h2 id="methods-config-title">Конфігурація методів для PII-колонок</h2>
              <p className="subtitle">
                Оберіть метод знеособлення для кожної виявленої колонки. Для HMAC колонка залишається персональною (псевдонімізація) і потребуватиме правової підстави для публікації.
              </p>
            </div>

            {/* Підказка щодо HMAC якщо вибрано хоча б одну таку колонку */}
            {hasHmac && (
              <div className="alert alert--warning" style={{ marginBottom: 'var(--space-4)' }}>
                <IconShield size={16} />
                <div className="alert__body">
                  <span className="alert__title">Псевдонімізація (HMAC)</span>
                  <span>
                    Вибрано метод HMAC: колонка лишається персональною, тому результуючий клас набору залишається <strong>Personal</strong>. Для публікації буде потрібна зареєстрована правова підстава (Legal Basis).
                  </span>
                </div>
              </div>
            )}

            {/* Попередження якщо не для всіх колонок вибрано метод */}
            {unconfiguredCount > 0 && (
              <div className="alert alert--warning" style={{ marginBottom: 'var(--space-4)' }}>
                <IconAlert size={16} />
                <div className="alert__body">
                  <span className="alert__title">Неповна обробка PII</span>
                  <span>
                    Увага: для {unconfiguredCount} колонок не вибрано метод. Ворота публікації (Publication Gate) не пропустять набір із залишковими відкритими персональними даними.
                  </span>
                </div>
              </div>
            )}

            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Колонка</th>
                    <th scope="col">Виявлений тип</th>
                    <th scope="col">Впевненість</th>
                    <th scope="col">Зразок</th>
                    <th scope="col" style={{ minWidth: '220px' }}>Метод анонімізації</th>
                    <th scope="col">Підказка до методу</th>
                  </tr>
                </thead>
                <tbody>
                  {findings.map((f) => {
                    const currentMethod = methods[f.column_name] ?? 'mask'
                    const piiType = f.corrected_pii_type ?? f.pii_type

                    return (
                      <tr key={f.column_name} className="anonymize-row">
                        <td>
                          <span className="col-name-mono">{f.column_name}</span>
                        </td>
                        <td>
                          <PiiTypeBadge type={piiType} />
                        </td>
                        <td>
                          <ConfidenceBar value={f.confidence} />
                        </td>
                        <td>
                          {f.sample_masked ? (
                            <code className="sample-masked">{f.sample_masked}</code>
                          ) : (
                            <span className="cell-muted">—</span>
                          )}
                        </td>
                        <td>
                          <select
                            className="filter-select method-select"
                            aria-label={`Метод анонімізації для ${f.column_name}`}
                            value={currentMethod}
                            onChange={(e) =>
                              handleMethodChange(
                                f.column_name,
                                e.target.value as AnonymizationMethodName,
                              )
                            }
                          >
                            {(Object.keys(ANONYMIZATION_METHOD_LABELS) as AnonymizationMethodName[]).map(
                              (m) => (
                                <option
                                  key={m}
                                  value={m}
                                  disabled={m === 'redact'}
                                  title={m === 'redact' ? 'Метод redact (видалення колонки) наразі не підтримується рушієм анонімізації бекенду' : undefined}
                                >
                                  {ANONYMIZATION_METHOD_LABELS[m]}
                                </option>
                              ),
                            )}
                          </select>
                        </td>
                        <td>
                          {currentMethod === 'hmac' && (
                            <span className="hmac-hint badge badge--warning" title="Псевдонімізація: зберігає аналітичну зв'язність, але потребує згоди або іншої правової підстави">
                              <IconShield size={12} />
                              <span>Потрібна правова підстава</span>
                            </span>
                          )}
                          {currentMethod === 'mask' && (
                            <span className="cell-muted" style={{ fontSize: '13px' }}>
                              Повна заміна на ***
                            </span>
                          )}
                          {currentMethod === 'generalize' && (
                            <span className="cell-muted" style={{ fontSize: '13px' }}>
                              Узагальнення до року/діапазону
                            </span>
                          )}
                          {currentMethod === 'redact' && (
                            <span className="cell-muted" style={{ fontSize: '13px', color: 'var(--color-danger)' }}>
                              Стовпець буде видалено
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Панель дій: прев'ю та застосування */}
            <div className="card__footer" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'var(--space-4)', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
              <div className="cell-muted" style={{ fontSize: '13px' }}>
                Колонок з налаштованим методом: {Object.keys(methods).length} з {findings.length}
              </div>
              <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
                <Button
                  variant="secondary"
                  onClick={handlePreview}
                  disabled={busy !== null}
                >
                  {busy === 'preview' ? 'Побудова прев\'ю…' : 'Попередній перегляд'}
                </Button>
                <Button
                  variant="primary"
                  onClick={handleApply}
                  disabled={!canApply}
                >
                  {busy === 'apply' ? 'Застосування…' : 'Застосувати анонімізацію'}
                </Button>
              </div>
            </div>
          </section>

          {/* Таблиця прев'ю «до / після» поруч */}
          {preview && (
            <section className="card anonymize-preview-section" aria-labelledby="preview-title" style={{ marginBottom: 'var(--space-6)' }}>
              <div className="page-header page-header--row">
                <div>
                  <h2 id="preview-title">Попередній перегляд «до / після»</h2>
                  <p className="subtitle">
                    Порівняння перших 10 рядків: оригінальні значення ліворуч та знеособлені праворуч із підсвічуванням змінених клітинок.
                  </p>
                </div>
                {preview.estimated_class && (
                  <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                    <span className="caption cell-muted">Очікуваний клас:</span>
                    <ClassBadge value={preview.estimated_class} />
                  </div>
                )}
              </div>

              {preview.preview_pairs && preview.preview_pairs.length > 0 ? (() => {
                const previewCols: string[] = preview.columns && preview.columns.length > 0
                  ? preview.columns.map((c) => c.column_name)
                  : findings.map((f) => f.column_name)

                return (
                  <div className="table-wrap diff-table-wrap">
                    <table className="table diff-table">
                      <thead>
                        <tr>
                          <th scope="col" style={{ width: '48px' }}>#</th>
                          {previewCols.map((colName) => (
                            <th key={colName} scope="col" colSpan={2} style={{ textAlign: 'center', borderLeft: '1px solid var(--color-line)' }}>
                              <span className="col-name-mono">{colName}</span>
                              <div className="caption cell-muted" style={{ fontWeight: 'normal', fontSize: '11px' }}>
                                метод: {ANONYMIZATION_METHOD_LABELS[methods[colName] ?? 'mask']}
                              </div>
                            </th>
                          ))}
                        </tr>
                        <tr className="diff-sub-header">
                          <th style={{ width: '48px' }} />
                          {previewCols.map((colName) => (
                            <th key={`sub-${colName}`} colSpan={2} style={{ padding: 0, borderLeft: '1px solid var(--color-line)' }}>
                              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', textAlign: 'center', fontSize: '11px' }}>
                                <span style={{ padding: '4px', background: 'var(--color-light)' }}>До</span>
                                <span style={{ padding: '4px', background: 'var(--sky-bg)', color: 'var(--sky-text)' }}>Після</span>
                              </div>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.preview_pairs.map((row) => (
                          <tr key={row.row_index}>
                            <td className="cell-muted" style={{ fontSize: '12px', textAlign: 'center' }}>
                              {row.row_index}
                            </td>
                            {previewCols.map((colName) => {
                              const origVal = row.original[colName] ?? '—'
                              const anonVal = row.anonymized[colName] ?? '—'
                              const isChanged = origVal !== anonVal

                              return (
                                <td key={`${row.row_index}-${colName}`} colSpan={2} style={{ padding: 0, borderLeft: '1px solid var(--color-line)' }}>
                                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', minHeight: '36px', alignItems: 'center' }}>
                                    <div className="cell-original" style={{ padding: '6px 8px', fontSize: '13px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={origVal}>
                                      {origVal}
                                    </div>
                                    <div
                                      className={`cell-anonymized ${isChanged ? 'cell-diff' : ''}`}
                                      style={{
                                        padding: '6px 8px',
                                        fontSize: '13px',
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        whiteSpace: 'nowrap',
                                        background: isChanged ? 'var(--sky-bg)' : 'transparent',
                                        color: isChanged ? 'var(--sky-text)' : 'inherit',
                                        fontWeight: isChanged ? 600 : 'normal',
                                      }}
                                      title={anonVal}
                                    >
                                      {anonVal}
                                    </div>
                                  </div>
                                </td>
                              )
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
              })() : (
                <div style={{ padding: 'var(--space-6)', textAlign: 'center' }}>
                  <p className="cell-muted" style={{ margin: 0 }}>
                    Бекенд не повернув рядків для попереднього перегляду.
                  </p>
                </div>
              )}

              <div className="card__footer" style={{ marginTop: 'var(--space-3)' }}>
                <span className="caption cell-muted">
                  Показано 10 перших рядків. Змінені значення підсвічено блакитним кольором.
                </span>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}
