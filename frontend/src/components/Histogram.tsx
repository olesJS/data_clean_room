import { useState } from 'react'
import type { ColumnHistogram } from '../api/types'

interface HistogramProps {
  data: ColumnHistogram
  columnName?: string
  min?: number | string | null
  max?: number | string | null
  mean?: number | null
  outliersCount?: number
  variant?: 'card' | 'mini'
}

export function Histogram({
  data,
  columnName,
  min,
  max,
  mean,
  outliersCount,
  variant = 'card',
}: HistogramProps) {
  const [activeBin, setActiveBin] = useState<number | null>(null)

  const { bins, counts } = data
  if (!bins || !counts || bins.length === 0 || counts.length === 0) {
    return <span className="cell-muted">Немає даних</span>
  }

  const maxCount = Math.max(...counts, 1)
  const totalCount = counts.reduce((acc, c) => acc + c, 0)

  if (variant === 'mini') {
    return (
      <div className="histogram-mini" title={`Розподіл для ${columnName ?? 'колонки'}`}>
        <div className="histogram-mini__bars">
          {counts.map((count, idx) => {
            const heightPct = Math.max(8, Math.round((count / maxCount) * 100))
            const isHighest = count === maxCount && count > 0
            return (
              <div
                key={idx}
                className={`histogram-mini__bar${isHighest ? ' is-peak' : ''}`}
                style={{ height: `${heightPct}%` }}
                title={`${bins[idx]}: ${count} (${totalCount > 0 ? ((count / totalCount) * 100).toFixed(1) : 0}%)`}
              />
            )
          })}
        </div>
        <span className="histogram-mini__meta">{bins.length} бакетів</span>
      </div>
    )
  }

  const active = activeBin !== null ? {
    bin: bins[activeBin],
    count: counts[activeBin],
    pct: totalCount > 0 ? ((counts[activeBin] / totalCount) * 100).toFixed(1) : '0',
  } : null

  return (
    <div className="histogram-card">
      <div className="histogram-card__header">
        <div className="histogram-card__title-row">
          <h4 className="histogram-card__title">
            Розподіл: <code>{columnName ?? 'Числова колонка'}</code>
          </h4>
          <span className="histogram-card__total">Загалом: {totalCount.toLocaleString('uk-UA')} значень</span>
        </div>

        <div className="histogram-card__stats">
          {min !== undefined && min !== null && (
            <span className="stat-pill" title="Мінімальне значення">
              <span className="stat-pill__label">Мін:</span>
              <span className="stat-pill__value">{typeof min === 'number' ? min.toLocaleString('uk-UA') : min}</span>
            </span>
          )}
          {mean !== undefined && mean !== null && (
            <span className="stat-pill" title="Середнє значення">
              <span className="stat-pill__label">Середнє:</span>
              <span className="stat-pill__value">{mean.toLocaleString('uk-UA')}</span>
            </span>
          )}
          {max !== undefined && max !== null && (
            <span className="stat-pill" title="Максимальне значення">
              <span className="stat-pill__label">Макс:</span>
              <span className="stat-pill__value">{typeof max === 'number' ? max.toLocaleString('uk-UA') : max}</span>
            </span>
          )}
          {outliersCount !== undefined && outliersCount > 0 && (
            <span className="stat-pill stat-pill--warn" title="Викиди за методом IQR (міжквартильний розмах)">
              <span className="stat-pill__label">Викиди (IQR):</span>
              <span className="stat-pill__value">{outliersCount}</span>
            </span>
          )}
        </div>
      </div>

      <div className="histogram-chart" role="region" aria-label={`Гістограма для ${columnName ?? 'колонки'}`}>
        <div className="histogram-chart__grid">
          <div className="histogram-chart__guideline" style={{ bottom: '75%' }} />
          <div className="histogram-chart__guideline" style={{ bottom: '50%' }} />
          <div className="histogram-chart__guideline" style={{ bottom: '25%' }} />
        </div>

        <div className="histogram-chart__bars">
          {counts.map((count, idx) => {
            const heightPct = Math.max(4, Math.round((count / maxCount) * 100))
            const isPeak = count === maxCount && count > 0
            const isHovered = activeBin === idx
            return (
              <div
                key={idx}
                className={`histogram-bar-col${isHovered ? ' is-hovered' : ''}`}
                onMouseEnter={() => setActiveBin(idx)}
                onMouseLeave={() => setActiveBin(null)}
                tabIndex={0}
                onFocus={() => setActiveBin(idx)}
                onBlur={() => setActiveBin(null)}
                aria-label={`${bins[idx]}: ${count}`}
              >
                <div className="histogram-bar-col__count">
                  {count > 0 ? count : ''}
                </div>
                <div className="histogram-bar-col__track">
                  <div
                    className={`histogram-bar-col__fill${isPeak ? ' is-peak' : ''}`}
                    style={{ height: `${heightPct}%` }}
                  />
                </div>
                <div className="histogram-bar-col__label" title={bins[idx]}>
                  {bins[idx]}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="histogram-card__footer">
        {active ? (
          <div className="histogram-card__detail">
            Інтервал: <strong>{active.bin}</strong> · Кількість: <strong>{active.count}</strong> (
            <strong>{active.pct}%</strong> від вибірки)
          </div>
        ) : (
          <div className="histogram-card__hint">
            Наведіть курсор або оберіть стовпець для деталей інтервалу
          </div>
        )}
      </div>
    </div>
  )
}
