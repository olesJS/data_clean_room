import type { DatasetProfileSummary } from '../api/types'

interface QualityScoreHeroProps {
  score: number
  summary: DatasetProfileSummary
}

export function QualityScoreHero({ score, summary }: QualityScoreHeroProps) {
  const level = score >= 80 ? 'high' : score >= 50 ? 'medium' : 'low'
  const label =
    level === 'high' ? 'Висока якість' : level === 'medium' ? 'Середня якість' : 'Низька якість'

  const { total_rows, rules_violated_count } = summary
  const cleanRows = Math.max(0, total_rows - rules_violated_count)
  const cleanPct = total_rows > 0 ? ((cleanRows / total_rows) * 100).toFixed(1) : '100'
  const defectPct = total_rows > 0 ? ((rules_violated_count / total_rows) * 100).toFixed(1) : '0'

  // Колове коло чи виразний круглий прогрес-індикатор
  const radius = 48
  const stroke = 8
  const normalizedRadius = radius - stroke * 2
  const circumference = normalizedRadius * 2 * Math.PI
  const strokeDashoffset = circumference - (Math.min(100, Math.max(0, score)) / 100) * circumference

  return (
    <section className={`quality-hero quality-hero--${level}`} aria-label="Показник Quality Score">
      <div className="quality-hero__main">
        <div className="quality-hero__gauge">
          <svg height={radius * 2} width={radius * 2} className="quality-hero__circle">
            <circle
              stroke="var(--color-line)"
              fill="transparent"
              strokeWidth={stroke}
              r={normalizedRadius}
              cx={radius}
              cy={radius}
            />
            <circle
              className="quality-hero__circle-fill"
              fill="transparent"
              strokeWidth={stroke}
              strokeDasharray={`${circumference} ${circumference}`}
              style={{ strokeDashoffset }}
              r={normalizedRadius}
              cx={radius}
              cy={radius}
            />
          </svg>
          <div className="quality-hero__score-wrap">
            <span className="quality-hero__value">{score}</span>
            <span className="quality-hero__max">/ 100</span>
          </div>
        </div>

        <div className="quality-hero__text">
          <div className="quality-hero__badge-row">
            <span className={`badge badge--quality-${level}`}>{label}</span>
            <span className="quality-hero__standard">Стандарт Спринту 2</span>
          </div>
          <h2 className="quality-hero__title">Оцінка якості набору</h2>
          <p className="quality-hero__desc">
            {level === 'high' && 'Набір демонструє високу чистоту даних. Більшість записів відповідає правилам якості.'}
            {level === 'medium' && 'Набір містить дефекти у деяких колонках. Рекомендується переглянути порушення перед публікацією.'}
            {level === 'low' && 'Критична кількість дефектів та порушень правил. Дані потребують виправлення перед подальшим використанням.'}
          </p>
        </div>
      </div>

      <div className="quality-hero__formula">
        <div className="formula-card">
          <div className="formula-card__header">
            <span className="formula-card__tag">Формула розрахунку</span>
            <code>Score = 100 × (N − N_пр) / N</code>
          </div>
          <div className="formula-card__calc">
            <span>100 × ({total_rows} − {rules_violated_count}) / {total_rows} = <strong>{score}</strong></span>
          </div>

          <div className="formula-breakdown">
            <div className="formula-breakdown__bar" role="progressbar" aria-label="Співвідношення чистих рядків до рядків з дефектами">
              <div
                className="formula-breakdown__clean"
                style={{ width: `${cleanPct}%` }}
                title={`Чисті рядки: ${cleanRows} (${cleanPct}%)`}
              />
              <div
                className="formula-breakdown__defect"
                style={{ width: `${defectPct}%` }}
                title={`Рядки з дефектами: ${rules_violated_count} (${defectPct}%)`}
              />
            </div>

            <div className="formula-breakdown__legend">
              <span className="legend-item">
                <span className="legend-dot legend-dot--clean" />
                <span>Чисті: <strong>{cleanRows}</strong> ({cleanPct}%)</span>
              </span>
              <span className="legend-item">
                <span className="legend-dot legend-dot--defect" />
                <span>З дефектами: <strong>{rules_violated_count}</strong> ({defectPct}%)</span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
