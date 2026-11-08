import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchDatasetProfile } from '../api/datasets'
import type { ColumnDataType, DatasetProfileResponse } from '../api/types'
import { ClassBadge } from '../components/Badges'
import { Button } from '../components/Button'
import { ErrorMessage } from '../components/ErrorMessage'
import { Histogram } from '../components/Histogram'
import { QualityScoreHero } from '../components/QualityScoreHero'
import {
  IconAlert,
  IconArrowLeft,
  IconBarChart,
  IconCheck,
  IconChevronDown,
  IconChevronUp,
  IconDatabase,
  IconRefresh,
  IconSearch,
  IconShield,
} from '../components/icons'

function TypeBadge({ type }: { type: ColumnDataType }) {
  const meta: Record<ColumnDataType, { label: string; cls: string; icon: string }> = {
    numeric: { label: 'Числовий', cls: 'badge--type-numeric', icon: '123' },
    string: { label: 'Текстовий', cls: 'badge--type-string', icon: 'ABC' },
    datetime: { label: 'Дата / час', cls: 'badge--type-datetime', icon: '📅' },
    boolean: { label: 'Булевий', cls: 'badge--type-boolean', icon: '✓/✗' },
  }
  const item = meta[type] ?? { label: type, cls: 'badge--type-string', icon: '•' }
  return (
    <span className={`badge badge--type ${item.cls}`} title={`Тип даних: ${item.label}`}>
      <span className="badge__type-icon" aria-hidden="true">{item.icon}</span>
      {item.label}
    </span>
  )
}

export default function ProfilePage() {
  const { id } = useParams<{ id: string }>()
  const datasetId = id ?? '1'

  const [profile, setProfile] = useState<DatasetProfileResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Фільтрація та вигляд
  const [query, setQuery] = useState('')
  const [selectedType, setSelectedType] = useState<string>('all')
  const [issuesOnly, setIssuesOnly] = useState(false)
  const [expandedCols, setExpandedCols] = useState<Record<string, boolean>>({})
  const [activeTab, setActiveTab] = useState<'columns' | 'histograms'>('columns')

  const loadProfile = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchDatasetProfile(datasetId)
      setProfile(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося завантажити профіль набору')
    } finally {
      setLoading(false)
    }
  }, [datasetId])

  useEffect(() => {
    loadProfile()
  }, [loadProfile])

  const toggleExpand = (colName: string) => {
    setExpandedCols((prev) => ({ ...prev, [colName]: !prev[colName] }))
  }

  const columns = useMemo(() => profile?.columns ?? [], [profile])

  // Числові колонки з гістограмами
  const numericHistogramColumns = useMemo(
    () => columns.filter((c) => c.histogram !== null),
    [columns]
  )

  // Фільтрація колонок
  const filteredColumns = useMemo(() => {
    return columns.filter((col) => {
      if (query.trim()) {
        const q = query.toLowerCase()
        const matchName = col.name.toLowerCase().includes(q)
        const matchPii = col.pii_type ? col.pii_type.toLowerCase().includes(q) : false
        if (!matchName && !matchPii) return false
      }
      if (selectedType !== 'all' && col.type !== selectedType) {
        return false
      }
      if (issuesOnly && col.null_count === 0 && col.outliers_count === 0) {
        return false
      }
      return true
    })
  }, [columns, query, selectedType, issuesOnly])

  const expandAllHistograms = () => {
    const next: Record<string, boolean> = {}
    for (const c of numericHistogramColumns) next[c.name] = true
    setExpandedCols(next)
  }

  const collapseAll = () => {
    setExpandedCols({})
  }

  return (
    <div className="profile-page">
      {/* Верхня навігація та заголовок */}
      <div className="page-header page-header--row">
        <div>
          <div className="profile-breadcrumbs">
            <Link to="/datasets" className="profile-breadcrumbs__link">
              <IconArrowLeft size={14} />
              <span>До списку наборів</span>
            </Link>
            <span className="profile-breadcrumbs__sep">/</span>
            <span className="profile-breadcrumbs__current">Профіль #{datasetId}</span>
          </div>

          <div className="profile-title-row">
            <h1>{profile ? profile.dataset_name : `Набір #${datasetId}`}</h1>
            {profile && <ClassBadge value={profile.data_class} />}
          </div>
          <p className="subtitle">
            Звіт профілювання колонок, дефектів та показника Quality Score (UC-03)
          </p>
        </div>

        <div className="profile-actions">
          <Link to={`/datasets/${datasetId}/quality`} className="btn btn--secondary">
            Правила якості
          </Link>
          <Link to={`/datasets/${datasetId}/pii`} className="btn btn--secondary">
            PII результати
          </Link>
          <Button variant="secondary" onClick={loadProfile} disabled={loading}>
            <IconRefresh size={16} />
            <span>Оновити</span>
          </Button>
        </div>
      </div>

      {/* Помилка завантаження */}
      {error && (
        <div className="profile-state">
          <ErrorMessage title="Не вдалося отримати звіт профілювання">{error}</ErrorMessage>
          <div className="actions" style={{ marginTop: 'var(--space-3)' }}>
            <Button onClick={loadProfile}>Спробувати знову</Button>
            <Link to="/datasets" className="btn btn--secondary">Повернутися до списку</Link>
          </div>
        </div>
      )}

      {/* Стан завантаження */}
      {loading && !profile && (
        <div className="profile-skeleton" aria-busy="true" aria-label="Завантаження звіту профілювання">
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

      {/* Основний вміст профілю */}
      {profile && (
        <>
          {/* Виразний Quality Score Hero */}
          <QualityScoreHero score={profile.quality_score} summary={profile.summary} />

          {/* Загальні метрики набору (KPI Summary) */}
          <div className="stats stats--4cols">
            <div className="stat">
              <span className="stat__label">Усього рядків</span>
              <span className="stat__value">{profile.summary.total_rows.toLocaleString('uk-UA')}</span>
              <span className="stat__hint">Обсяг вибірки набору</span>
            </div>

            <div className="stat">
              <span className="stat__label">Кількість колонок</span>
              <span className="stat__value">{profile.summary.total_columns}</span>
              <span className="stat__hint">
                {profile.columns.filter((c) => c.type === 'numeric').length} числових ·{' '}
                {profile.columns.filter((c) => c.type === 'string').length} текстових
              </span>
            </div>

            <div className="stat">
              <span className="stat__label">Дублікати рядків</span>
              <span className={`stat__value${profile.summary.duplicate_rows_count > 0 ? ' stat__value--warn' : ' stat__value--ok'}`}>
                {profile.summary.duplicate_rows_count}
              </span>
              <span className="stat__hint">
                {profile.summary.duplicate_rows_count > 0 ? 'Потребують дедуплікації' : 'Дублікатів не виявлено'}
              </span>
            </div>

            <div className="stat">
              <span className="stat__label">Рядки з порушеннями правил</span>
              <span className={`stat__value${profile.summary.rules_violated_count > 0 ? ' stat__value--warn' : ' stat__value--ok'}`}>
                {profile.summary.rules_violated_count}
              </span>
              <span className="stat__hint">Враховуються у Quality Score</span>
            </div>
          </div>

          {/* Перемикач вкладок між таблицею та галереєю гістограм */}
          <div className="tabs-header">
            <div className="tabs-nav" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'columns'}
                className={`tab-btn${activeTab === 'columns' ? ' is-active' : ''}`}
                onClick={() => setActiveTab('columns')}
              >
                <IconDatabase size={16} />
                <span>Таблиця колонок ({columns.length})</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'histograms'}
                className={`tab-btn${activeTab === 'histograms' ? ' is-active' : ''}`}
                onClick={() => setActiveTab('histograms')}
              >
                <IconBarChart size={16} />
                <span>Гістограми розподілу ({numericHistogramColumns.length})</span>
              </button>
            </div>

            {activeTab === 'columns' && numericHistogramColumns.length > 0 && (
              <div className="tabs-extra">
                <button
                  type="button"
                  className="btn-link"
                  onClick={expandAllHistograms}
                >
                  Розгорнути всі гістограми
                </button>
                <span className="cell-muted">·</span>
                <button
                  type="button"
                  className="btn-link"
                  onClick={collapseAll}
                >
                  Згорнути
                </button>
              </div>
            )}
          </div>

          {activeTab === 'columns' && (
            <section className="card card--table-section">
              {/* Панель фільтрів і пошуку */}
              <div className="table-toolbar">
                <div className="table-toolbar__search">
                  <IconSearch size={16} />
                  <input
                    type="search"
                    placeholder="Пошук колонки за назвою або PII..."
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
                    <span>Тип:</span>
                    <select
                      value={selectedType}
                      onChange={(e) => setSelectedType(e.target.value)}
                      className="filter-select"
                    >
                      <option value="all">Усі типи ({columns.length})</option>
                      <option value="numeric">Числові</option>
                      <option value="string">Текстові</option>
                      <option value="datetime">Дата/час</option>
                      <option value="boolean">Булеві</option>
                    </select>
                  </label>

                  <label className="filter-checkbox-label">
                    <input
                      type="checkbox"
                      checked={issuesOnly}
                      onChange={(e) => setIssuesOnly(e.target.checked)}
                    />
                    <span>Тільки з пропусками чи викидами</span>
                  </label>
                </div>
              </div>

              {/* Таблиця колонок */}
              <div className="table-wrap">
                <table className="table table--profile">
                  <thead>
                    <tr>
                      <th style={{ width: '36px' }} aria-label="Розгорнути" />
                      <th scope="col">Назва колонки</th>
                      <th scope="col">Тип</th>
                      <th scope="col">Пропуски (Nulls)</th>
                      <th scope="col">Унікальні</th>
                      <th scope="col">Викиди (IQR)</th>
                      <th scope="col">Статистика (Мін / Макс / Сер.)</th>
                      <th scope="col">Розподіл</th>
                      <th scope="col">PII статус</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredColumns.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="table__empty">
                          За заданими фільтрами колонок не знайдено
                        </td>
                      </tr>
                    ) : (
                      filteredColumns.map((col) => {
                        const isExpanded = !!expandedCols[col.name]
                        const hasNulls = col.null_count > 0
                        const hasOutliers = col.outliers_count > 0
                        const hasHistogram = col.histogram !== null

                        return (
                          <tr key={col.name} className="profile-row-group">
                            <td colSpan={9} style={{ padding: 0, border: 0 }}>
                              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <tbody>
                                  <tr className={`profile-row${isExpanded ? ' is-expanded' : ''}`}>
                                    <td style={{ width: '36px', textAlign: 'center' }}>
                                      {hasHistogram ? (
                                        <button
                                          type="button"
                                          className="btn-icon-toggle"
                                          onClick={() => toggleExpand(col.name)}
                                          aria-expanded={isExpanded}
                                          title={isExpanded ? 'Згорнути гістограму' : 'Розгорнути гістограму'}
                                        >
                                          {isExpanded ? <IconChevronUp size={16} /> : <IconChevronDown size={16} />}
                                        </button>
                                      ) : (
                                        <span className="cell-muted" style={{ fontSize: '11px' }}>—</span>
                                      )}
                                    </td>

                                    <td>
                                      <div className="col-name-cell">
                                        <strong className="col-name-cell__title">{col.name}</strong>
                                        {col.is_pii && (
                                          <span className="badge badge--pii-pill" title="Виявлено персональні дані">
                                            <IconShield size={11} />
                                            PII
                                          </span>
                                        )}
                                      </div>
                                    </td>

                                    <td>
                                      <TypeBadge type={col.type} />
                                    </td>

                                    <td>
                                      <div className="cell-metric">
                                        <span className={`cell-metric__value${hasNulls ? ' is-warn' : ''}`}>
                                          {col.null_count} ({col.null_percentage.toFixed(1)}%)
                                        </span>
                                        {hasNulls && (
                                          <div className="cell-metric__bar" title={`Пропуски: ${col.null_percentage}%`}>
                                            <div
                                              className="cell-metric__bar-fill"
                                              style={{ width: `${Math.min(100, Math.max(8, col.null_percentage))}%` }}
                                            />
                                          </div>
                                        )}
                                      </div>
                                    </td>

                                    <td>
                                      <div className="cell-two">
                                        <span className="cell-strong">{col.unique_count.toLocaleString('uk-UA')}</span>
                                        <small className="cell-muted">
                                          {profile.summary.total_rows > 0
                                            ? `${((col.unique_count / profile.summary.total_rows) * 100).toFixed(1)}% унікальності`
                                            : ''}
                                        </small>
                                      </div>
                                    </td>

                                    <td>
                                      {hasOutliers ? (
                                        <span className="badge badge--attention" title="Статистичні викиди за методом IQR (міжквартильний розмах)">
                                          <IconAlert size={12} />
                                          {col.outliers_count} викидів
                                        </span>
                                      ) : (
                                        <span className="cell-muted">0</span>
                                      )}
                                    </td>

                                    <td>
                                      {col.type === 'numeric' || col.type === 'datetime' ? (
                                        <div className="cell-stats">
                                          <div>
                                            <span className="cell-muted">Мін:</span>{' '}
                                            <strong>{typeof col.min === 'number' ? col.min.toLocaleString('uk-UA') : col.min ?? '—'}</strong>
                                          </div>
                                          {col.mean !== null && (
                                            <div>
                                              <span className="cell-muted">Сер:</span>{' '}
                                              <strong>{col.mean.toLocaleString('uk-UA')}</strong>
                                            </div>
                                          )}
                                          <div>
                                            <span className="cell-muted">Макс:</span>{' '}
                                            <strong>{typeof col.max === 'number' ? col.max.toLocaleString('uk-UA') : col.max ?? '—'}</strong>
                                          </div>
                                        </div>
                                      ) : (
                                        <span className="cell-muted">—</span>
                                      )}
                                    </td>

                                    <td>
                                      {hasHistogram && col.histogram ? (
                                        <div
                                          className="cell-histogram-preview"
                                          onClick={() => toggleExpand(col.name)}
                                          role="button"
                                          tabIndex={0}
                                          onKeyDown={(e) => {
                                            if (e.key === 'Enter' || e.key === ' ') toggleExpand(col.name)
                                          }}
                                          title="Натисніть для перегляду повної гістограми"
                                        >
                                          <Histogram data={col.histogram} columnName={col.name} variant="mini" />
                                        </div>
                                      ) : (
                                        <span className="cell-muted">—</span>
                                      )}
                                    </td>

                                    <td>
                                      {col.is_pii ? (
                                        <div className="pii-cell">
                                          <span className="badge badge--pii">
                                            {col.pii_type ?? 'PII'}
                                          </span>
                                          {col.pii_confidence !== null && (
                                            <small className="cell-muted">
                                              conf: {Math.round(col.pii_confidence * 100)}%
                                            </small>
                                          )}
                                        </div>
                                      ) : (
                                        <span className="cell-muted" title="Персональних даних не знайдено">
                                          <IconCheck size={14} /> Ні
                                        </span>
                                      )}
                                    </td>
                                  </tr>

                                  {/* Розгорнутий рядок з повною гістограмою */}
                                  {isExpanded && col.histogram && (
                                    <tr className="profile-expanded-row">
                                      <td colSpan={9}>
                                        <div className="expanded-histogram-box">
                                          <Histogram
                                            data={col.histogram}
                                            columnName={col.name}
                                            min={col.min}
                                            max={col.max}
                                            mean={col.mean}
                                            outliersCount={col.outliers_count}
                                            variant="card"
                                          />
                                        </div>
                                      </td>
                                    </tr>
                                  )}
                                </tbody>
                              </table>
                            </td>
                          </tr>
                        )
                      })
                    )}
                  </tbody>
                </table>
              </div>

              <div className="card__footer">
                <span className="caption">
                  Показано {filteredColumns.length} з {columns.length} колонок · Викиди визначено методом IQR (1.5 × IQR)
                </span>
              </div>
            </section>
          )}

          {/* Вкладка: Галерея всіх гістограм числових колонок */}
          {activeTab === 'histograms' && (
            <section className="histograms-gallery">
              {numericHistogramColumns.length === 0 ? (
                <div className="empty" style={{ minHeight: '260px' }}>
                  <h3>Немає числових колонок з гістограмами</h3>
                  <p>Усі колонки цього набору є текстовими або не містять числових розподілів.</p>
                </div>
              ) : (
                <div className="histograms-grid">
                  {numericHistogramColumns.map((col) => (
                    <div key={col.name} className="histogram-grid-item">
                      {col.histogram && (
                        <Histogram
                          data={col.histogram}
                          columnName={col.name}
                          min={col.min}
                          max={col.max}
                          mean={col.mean}
                          outliersCount={col.outliers_count}
                          variant="card"
                        />
                      )}
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  )
}
