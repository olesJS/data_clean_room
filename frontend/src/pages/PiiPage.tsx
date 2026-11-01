import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchPiiScan, updatePiiColumn } from '../api/datasets'
import type { PiiFinding, PiiScanResponse, PiiType, PiiUpdatePayload } from '../api/types'
import { ClassBadge } from '../components/Badges'
import { Button } from '../components/Button'
import { ErrorMessage } from '../components/ErrorMessage'
import {
  IconArrowLeft,
  IconCheck,
  IconEdit,
  IconRefresh,
  IconSearch,
  IconShield,
  IconX,
} from '../components/icons'

// ─── Константи ────────────────────────────────────────────────────────────────

const PII_TYPE_LABELS: Record<Exclude<PiiType, null>, string> = {
  UA_IPN: 'ІПН (Україна)',
  UA_FULL_NAME: "Повне ім'я",
  UA_IBAN: 'IBAN (Україна)',
  UA_PHONE: 'Телефон (UA)',
  UA_PASSPORT: 'Паспорт (UA)',
  EMAIL: 'Електронна пошта',
  CREDIT_CARD: 'Банківська картка',
  DATE_OF_BIRTH: 'Дата народження',
  UA_ADDRESS: 'Адреса (Україна)',
}

const ALL_PII_TYPES: Exclude<PiiType, null>[] = [
  'UA_IPN',
  'UA_FULL_NAME',
  'UA_IBAN',
  'UA_PHONE',
  'UA_PASSPORT',
  'EMAIL',
  'CREDIT_CARD',
  'DATE_OF_BIRTH',
  'UA_ADDRESS',
]

const METHOD_LABELS: Record<string, string> = {
  regex: 'Регулярний вираз',
  'regex+checksum': 'Regex + контрольна цифра',
  'regex+luhn': 'Regex + алгоритм Луна',
  dictionary: 'Словникова атака',
  'column_name+regex': 'Назва колонки + Regex',
}

function formatMethod(m: string): string {
  return METHOD_LABELS[m] ?? m
}

// ─── Допоміжні компоненти ────────────────────────────────────────────────────

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
      <div className="confidence-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className={`confidence-bar__fill confidence-bar__fill--${level}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function StatusBadgePii({ confirmed }: { confirmed: boolean | null }) {
  if (confirmed === null)
    return <span className="pii-status pii-status--pending">Очікує рев'ю</span>
  if (confirmed)
    return <span className="pii-status pii-status--confirmed">Підтверджено</span>
  return <span className="pii-status pii-status--rejected">Відхилено</span>
}

// ─── Рядок таблиці ───────────────────────────────────────────────────────────

interface RowProps {
  finding: PiiFinding
  datasetId: string
  onUpdate: (updated: PiiFinding) => void
}

function FindingRow({ finding, datasetId, onUpdate }: RowProps) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [correcting, setCorrecting] = useState(false)
  const [selectedType, setSelectedType] = useState<Exclude<PiiType, null>>(
    (finding.corrected_pii_type ?? finding.pii_type ?? 'UA_IPN') as Exclude<PiiType, null>
  )

  const save = useCallback(
    async (payload: PiiUpdatePayload) => {
      setSaving(true)
      setError(null)
      try {
        const updated = await updatePiiColumn(datasetId, finding.column_name, payload)
        onUpdate(updated)
        setCorrecting(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Не вдалося зберегти зміни')
      } finally {
        setSaving(false)
      }
    },
    [datasetId, finding.column_name, onUpdate]
  )

  const handleConfirm = () => save({ user_confirmed: true })
  const handleReject = () => save({ user_confirmed: false })
  const handleCorrectSubmit = () =>
    save({ user_confirmed: true, corrected_pii_type: selectedType })

  const displayType = finding.corrected_pii_type ?? finding.pii_type

  return (
    <>
      <tr className={`pii-row${finding.user_confirmed === false ? ' pii-row--rejected' : ''}`}>
        <td>
          <span className="col-name-mono">{finding.column_name}</span>
        </td>
        <td>
          <PiiTypeBadge type={displayType} />
          {finding.corrected_pii_type && finding.corrected_pii_type !== finding.pii_type && (
            <div className="pii-correction-hint">
              <span className="cell-muted" style={{ fontSize: '11px' }}>
                Авто: {finding.pii_type ? (PII_TYPE_LABELS[finding.pii_type] ?? finding.pii_type) : '—'}
              </span>
            </div>
          )}
        </td>
        <td>
          <ConfidenceBar value={finding.confidence} />
        </td>
        <td>
          <span className="cell-muted" style={{ fontSize: '13px' }}>
            {formatMethod(finding.detection_method)}
          </span>
        </td>
        <td>
          {finding.sample_masked ? (
            <code className="sample-masked">{finding.sample_masked}</code>
          ) : (
            <span className="cell-muted">—</span>
          )}
        </td>
        <td>
          <StatusBadgePii confirmed={finding.user_confirmed} />
        </td>
        <td>
          <div className="pii-actions">
            {!correcting && (
              <>
                <button
                  type="button"
                  className="btn btn--sm btn--success"
                  onClick={handleConfirm}
                  disabled={saving || finding.user_confirmed === true}
                  title="Підтвердити автоматичну класифікацію"
                >
                  <IconCheck size={14} />
                  <span>Підтвердити</span>
                </button>
                <button
                  type="button"
                  className="btn btn--sm btn--secondary"
                  onClick={() => setCorrecting(true)}
                  disabled={saving}
                  title="Виправити тип PII"
                >
                  <IconEdit size={14} />
                  <span>Виправити</span>
                </button>
                <button
                  type="button"
                  className="btn btn--sm btn--danger-soft"
                  onClick={handleReject}
                  disabled={saving || finding.user_confirmed === false}
                  title="Відхилити — позначити як не-PII"
                >
                  <IconX size={14} />
                  <span>Не PII</span>
                </button>
              </>
            )}
          </div>
          {error && <p className="pii-row-error">{error}</p>}
        </td>
      </tr>
      {correcting && (
        <tr className="pii-correct-row">
          <td colSpan={7}>
            <div className="pii-correct-panel">
              <label className="pii-correct-label" htmlFor={`correct-${finding.column_name}`}>
                Виберіть правильний тип PII для <strong>{finding.column_name}</strong>:
              </label>
              <div className="pii-correct-controls">
                <select
                  id={`correct-${finding.column_name}`}
                  className="pii-correct-select"
                  value={selectedType}
                  onChange={(e) => setSelectedType(e.target.value as Exclude<PiiType, null>)}
                >
                  {ALL_PII_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {PII_TYPE_LABELS[t]}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="btn btn--sm btn--success"
                  onClick={handleCorrectSubmit}
                  disabled={saving}
                >
                  <IconCheck size={14} />
                  <span>{saving ? 'Збереження…' : 'Зберегти'}</span>
                </button>
                <button
                  type="button"
                  className="btn btn--sm btn--secondary"
                  onClick={() => setCorrecting(false)}
                  disabled={saving}
                >
                  Скасувати
                </button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

// ─── Головна сторінка ─────────────────────────────────────────────────────────

export default function PiiPage() {
  const { id } = useParams<{ id: string }>()
  const datasetId = id ?? '1'

  const [scan, setScan] = useState<PiiScanResponse | null>(null)
  const [findings, setFindings] = useState<PiiFinding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [filterStatus, setFilterStatus] = useState<'all' | 'pending' | 'confirmed' | 'rejected'>('all')

  const loadScan = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchPiiScan(datasetId)
      setScan(data)
      setFindings(data.findings)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося завантажити результати PII-сканування')
    } finally {
      setLoading(false)
    }
  }, [datasetId])

  useEffect(() => {
    loadScan()
  }, [loadScan])

  const handleUpdate = useCallback((updated: PiiFinding) => {
    setFindings((prev) =>
      prev.map((f) => (f.column_name === updated.column_name ? updated : f))
    )
  }, [])

  const filteredFindings = useMemo(() => {
    return findings.filter((f) => {
      if (query.trim()) {
        const q = query.toLowerCase()
        const matchCol = f.column_name.toLowerCase().includes(q)
        const matchType = f.pii_type ? f.pii_type.toLowerCase().includes(q) : false
        const matchLabel = f.pii_type ? (PII_TYPE_LABELS[f.pii_type] ?? '').toLowerCase().includes(q) : false
        if (!matchCol && !matchType && !matchLabel) return false
      }
      if (filterStatus === 'pending' && f.user_confirmed !== null) return false
      if (filterStatus === 'confirmed' && f.user_confirmed !== true) return false
      if (filterStatus === 'rejected' && f.user_confirmed !== false) return false
      return true
    })
  }, [findings, query, filterStatus])

  const stats = useMemo(() => {
    const pending = findings.filter((f) => f.user_confirmed === null).length
    const confirmed = findings.filter((f) => f.user_confirmed === true).length
    const rejected = findings.filter((f) => f.user_confirmed === false).length
    const avgConf = findings.length > 0
      ? (findings.reduce((acc, f) => acc + f.confidence, 0) / findings.length * 100).toFixed(1)
      : '—'
    return { pending, confirmed, rejected, avgConf }
  }, [findings])

  const allReviewed = findings.length > 0 && stats.pending === 0

  return (
    <div className="pii-page">
      {/* Верхня навігація та заголовок */}
      <div className="page-header page-header--row">
        <div>
          <div className="pii-breadcrumbs">
            <Link to="/datasets" className="pii-breadcrumbs__link">
              <IconArrowLeft size={14} />
              <span>До списку наборів</span>
            </Link>
            <span className="pii-breadcrumbs__sep">/</span>
            <span className="pii-breadcrumbs__current">PII сканування #{datasetId}</span>
          </div>
          <div className="pii-title-row">
            <h1>{scan ? scan.dataset_name : `Набір #${datasetId}`}</h1>
            {scan && <ClassBadge value={scan.data_class} />}
          </div>
          <p className="subtitle">
            Результати PII-сканування: виявлені персональні дані по колонках (UC-04)
          </p>
        </div>
        <button
          type="button"
          className="btn btn--secondary"
          onClick={loadScan}
          disabled={loading}
        >
          <IconRefresh size={16} />
          <span>Оновити</span>
        </button>
      </div>

      {/* Помилка завантаження */}
      {error && (
        <div>
          <ErrorMessage title="Не вдалося отримати результати PII-сканування">{error}</ErrorMessage>
          <div className="actions" style={{ marginTop: 'var(--space-3)' }}>
            <Button onClick={loadScan}>Спробувати знову</Button>
            <Link to="/datasets" className="btn btn--secondary">До списку наборів</Link>
          </div>
        </div>
      )}

      {/* Скелетон */}
      {loading && !scan && (
        <div className="pii-skeleton" aria-busy="true" aria-label="Завантаження результатів PII">
          <div className="skeleton-card skeleton-card--hero" />
          <div className="stats">
            <div className="skeleton-card" />
            <div className="skeleton-card" />
            <div className="skeleton-card" />
            <div className="skeleton-card" />
          </div>
          <div className="skeleton-card skeleton-card--table" />
        </div>
      )}

      {scan && (
        <>
          {/* Банер пояснення класу даних */}
          <div className={`pii-class-alert pii-class-alert--${scan.data_class.toLowerCase()}`} role="note">
            <IconShield size={18} />
            <div>
              <strong>Клас набору: {scan.data_class}</strong>
              {scan.data_class === 'Personal' && (
                <p>
                  Набір класифіковано як <strong>Personal</strong>, оскільки містить{' '}
                  {scan.pii_columns_count} {scan.pii_columns_count === 1 ? 'колонку' : 'колонок'} із персональними даними.
                  Перед публікацією підтвердіть або виправте автоматичну класифікацію.
                </p>
              )}
              {scan.data_class === 'Confidential' && (
                <p>Набір містить конфіденційну інформацію. Усі PII-колонки слід анонімізувати перед публікацією.</p>
              )}
              {(scan.data_class === 'Public' || scan.data_class === 'Internal') && (
                <p>PII-ризики для цього набору оцінено як низькі. Перевірте знахідки нижче.</p>
              )}
            </div>
            {allReviewed && (
              <span className="pii-class-alert__done">
                <IconCheck size={14} /> Усі колонки перевірено
              </span>
            )}
          </div>

          {/* KPI Stats */}
          <div className="stats stats--4cols">
            <div className="stat">
              <span className="stat__label">PII-колонок знайдено</span>
              <span className="stat__value stat__value--warn">{scan.pii_columns_count}</span>
              <span className="stat__hint">з {scan.total_columns} колонок набору</span>
            </div>
            <div className="stat">
              <span className="stat__label">Очікують рев'ю</span>
              <span className={`stat__value${stats.pending > 0 ? ' stat__value--warn' : ' stat__value--ok'}`}>
                {stats.pending}
              </span>
              <span className="stat__hint">потрібне підтвердження</span>
            </div>
            <div className="stat">
              <span className="stat__label">Підтверджено</span>
              <span className="stat__value stat__value--ok">{stats.confirmed}</span>
              <span className="stat__hint">вручну верифіковано</span>
            </div>
            <div className="stat">
              <span className="stat__label">Середня впевненість</span>
              <span className="stat__value">{stats.avgConf}%</span>
              <span className="stat__hint">автоматичної детекції</span>
            </div>
          </div>

          {/* Таблиця знахідок */}
          <section className="card card--table-section">
            {/* Панель фільтрів */}
            <div className="table-toolbar">
              <div className="table-toolbar__search">
                <IconSearch size={16} />
                <input
                  type="search"
                  placeholder="Пошук за назвою колонки або типом PII…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="table-toolbar__input"
                />
                {query && (
                  <button
                    type="button"
                    className="table-toolbar__clear"
                    onClick={() => setQuery('')}
                    aria-label="Очистити пошук"
                  >
                    ×
                  </button>
                )}
              </div>
              <div className="table-toolbar__filters">
                <label className="filter-select-label">
                  <span>Статус рев'ю:</span>
                  <select
                    value={filterStatus}
                    onChange={(e) => setFilterStatus(e.target.value as typeof filterStatus)}
                    className="filter-select"
                  >
                    <option value="all">Усі ({findings.length})</option>
                    <option value="pending">Очікують ({stats.pending})</option>
                    <option value="confirmed">Підтверджені ({stats.confirmed})</option>
                    <option value="rejected">Відхилені ({stats.rejected})</option>
                  </select>
                </label>
              </div>
            </div>

            {/* Таблиця */}
            <div className="table-wrap">
              <table className="table table--pii">
                <thead>
                  <tr>
                    <th scope="col">Колонка</th>
                    <th scope="col">Тип PII</th>
                    <th scope="col">Впевненість</th>
                    <th scope="col">Метод виявлення</th>
                    <th scope="col">Приклад (маскований)</th>
                    <th scope="col">Статус</th>
                    <th scope="col">Дії</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredFindings.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="table__empty">
                        {findings.length === 0
                          ? 'PII-колонок у цьому наборі не виявлено'
                          : 'За заданими фільтрами знахідок не знайдено'}
                      </td>
                    </tr>
                  ) : (
                    filteredFindings.map((f) => (
                      <FindingRow
                        key={f.column_name}
                        finding={f}
                        datasetId={datasetId}
                        onUpdate={handleUpdate}
                      />
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="card__footer">
              <span className="caption">
                Показано {filteredFindings.length} з {findings.length} знахідок ·{' '}
                Впевненість ≥ 90% — висока, 70–89% — середня, &lt;70% — низька
              </span>
            </div>
          </section>

          {/* Нижній підказ якщо є неперевірені */}
          {stats.pending > 0 && (
            <div className="alert alert--warning">
              <IconShield size={16} />
              <div className="alert__body">
                <span className="alert__title">Потрібна дія</span>
                <span>
                  Залишилось {stats.pending} {stats.pending === 1 ? 'знахідка' : 'знахідок'} без рев'ю.
                  Підтвердьте або виправте класифікацію перед публікацією набору.
                </span>
              </div>
            </div>
          )}
          {allReviewed && (
            <div className="alert alert--success">
              <IconCheck size={16} />
              <div className="alert__body">
                <span className="alert__title">Рев'ю завершено</span>
                <span>Усі PII-знахідки перевірено. Набір готовий до наступного кроку обробки.</span>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
