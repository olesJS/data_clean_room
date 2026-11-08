// frontend/src/pages/QualityRulesPage.tsx
// Екран «Правила якості та порушення набору» (UC-04, SCRUM-49).
// Маршрут: /datasets/:id/quality. Стилі: блок «Quality rules» у styles/global.css.

import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getQualityReport, getQualityRules } from '../api/quality'
import type { QualityAction, QualityReport, QualityRule, QualityViolation } from '../api/types'

const ACTIONS: QualityAction[] = ['reject', 'flag', 'block']

const ACTION_META: Record<QualityAction, { hint: string; impact: string }> = {
  reject: { hint: 'Рядок відхиляється', impact: 'Відхиляє рядок' },
  flag: { hint: 'Рядок позначається для перевірки', impact: 'Позначає рядок' },
  block: { hint: 'Публікація набору блокується', impact: 'Блокує публікацію' },
}

const integer = new Intl.NumberFormat('uk-UA')
const oneDecimal = new Intl.NumberFormat('uk-UA', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

type ScoreTone = 'high' | 'medium' | 'low'

// Пороги ті самі, що в списку наборів: ≥80 висока, 50–79 середня, <50 низька.
function scoreTone(score: number): { tone: ScoreTone; label: string } {
  if (score >= 80) return { tone: 'high', label: 'Висока якість' }
  if (score >= 50) return { tone: 'medium', label: 'Середня якість' }
  return { tone: 'low', label: 'Низька якість' }
}

const columnLabel = (column: string): string => (column === '*' ? 'Весь рядок' : column)

function errorStatus(error: unknown): number | undefined {
  const status = (error as { status?: unknown } | null)?.status
  return typeof status === 'number' ? status : undefined
}

function describeError(status: number | undefined): { title: string; text: string; retry: boolean } {
  if (status === 404) {
    return {
      title: 'Правила й порушення для цього набору недоступні',
      text: 'Після налаштування правил якості та профілювання тут з’являться результати перевірки.',
      retry: false,
    }
  }
  if (status === 403) {
    return {
      title: 'Немає доступу до цього набору',
      text: 'Правила й порушення бачить власник набору та Data Steward.',
      retry: false,
    }
  }
  return { title: 'Не вдалося завантажити дані', text: 'Перевірте з’єднання та спробуйте ще раз.', retry: true }
}

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; httpStatus?: number }
  | { status: 'success'; rules: QualityRule[]; report: QualityReport }

function useQualityData(datasetId: string | undefined): [LoadState, () => void] {
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!datasetId) return
    let cancelled = false
    setState({ status: 'loading' })
    Promise.all([getQualityRules(datasetId), getQualityReport(datasetId)])
      .then(([rules, report]) => {
        if (!cancelled) setState({ status: 'success', rules, report })
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ status: 'error', httpStatus: errorStatus(error) })
      })
    return () => {
      cancelled = true
    }
  }, [datasetId, attempt])

  return [state, () => setAttempt((n) => n + 1)]
}

function ActionBadge({ action }: { action: QualityAction }) {
  return <span className={`qr-badge qr-badge--${action}`}>{action}</span>
}

function StatCard({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="qr-card">
      <p className="qr-stat__label">{label}</p>
      <p className="qr-stat__value">{value}</p>
      {note ? <p className="qr-stat__note">{note}</p> : null}
    </div>
  )
}

function ScoreCard({ score }: { score: number }) {
  const { tone, label } = scoreTone(score)
  return (
    <div className="qr-card qr-score" data-tone={tone}>
      <p className="qr-stat__label">Quality Score</p>
      <p className="qr-score__value">
        {oneDecimal.format(score)}
        <span className="qr-score__max"> / 100</span>
      </p>
      <p className="qr-stat__note">{label}</p>
    </div>
  )
}

interface ActionCardProps {
  action: QualityAction
  count: number
  selected: boolean
  onToggle: () => void
}

function ActionCard({ action, count, selected, onToggle }: ActionCardProps) {
  return (
    <button type="button" className="qr-action-card" aria-pressed={selected} onClick={onToggle}>
      <span className="qr-action-card__top">
        <ActionBadge action={action} />
        <span className="qr-action-card__count">{integer.format(count)}</span>
      </span>
      <span className="qr-action-card__hint">{ACTION_META[action].hint}</span>
    </button>
  )
}

function ViolationsTable({ violations }: { violations: QualityViolation[] }) {
  return (
    <div className="qr-table-wrap">
      <table className="qr-table">
        <thead>
          <tr>
            <th scope="col">Колонка</th>
            <th scope="col">Умова</th>
            <th scope="col">Дія</th>
            <th scope="col" className="qr-num">Порушень</th>
            <th scope="col">Вплив</th>
          </tr>
        </thead>
        <tbody>
          {violations.map((v) => (
            <tr key={`${v.column}|${v.condition}|${v.action}`}>
              <td className={v.column === '*' ? undefined : 'qr-mono'}>{columnLabel(v.column)}</td>
              <td><code className="qr-code">{v.condition}</code></td>
              <td><ActionBadge action={v.action} /></td>
              <td className="qr-num">{integer.format(v.violation_count)}</td>
              <td className={v.is_blocking ? 'qr-impact qr-impact--blocking' : 'qr-impact'}>
                {ACTION_META[v.action].impact}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RulesTable({ rules }: { rules: QualityRule[] }) {
  return (
    <div className="qr-table-wrap">
      <table className="qr-table">
        <thead>
          <tr>
            <th scope="col">Колонка</th>
            <th scope="col">Умова</th>
            <th scope="col">Дія</th>
            <th scope="col">Опис</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => (
            <tr key={`${rule.column}|${rule.condition}|${rule.action}`}>
              <td className={rule.column === '*' ? undefined : 'qr-mono'}>{columnLabel(rule.column)}</td>
              <td><code className="qr-code">{rule.condition}</code></td>
              <td><ActionBadge action={rule.action} /></td>
              <td className="qr-muted">{rule.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <div className="qr-empty">
      <p className="qr-empty__title">{title}</p>
      <p className="qr-empty__text">{text}</p>
    </div>
  )
}

function Report({ rules, report }: { rules: QualityRule[]; report: QualityReport }) {
  const [selected, setSelected] = useState<QualityAction | null>(null)

  const visible = useMemo(
    () => (selected ? report.violations.filter((v) => v.action === selected) : report.violations),
    [report.violations, selected],
  )
  const duplicateRows = report.summary?.duplicate_rows_count

  return (
    <>
      <section className="qr-stats" aria-label="Підсумок перевірки">
        <ScoreCard score={report.score} />
        <StatCard label="Рядків перевірено" value={integer.format(report.total_rows)} />
        <StatCard
          label="Рядків із порушеннями"
          value={integer.format(report.unique_violating_rows)}
          note="Кожен рядок рахується один раз"
        />
        {duplicateRows !== undefined ? (
          <StatCard label="Дублікатів" value={integer.format(duplicateRows)} />
        ) : null}
      </section>

      {!report.can_publish ? (
        <div className="qr-banner" role="status">
          <p className="qr-banner__title">Публікацію заблоковано</p>
          <p className="qr-banner__text">
            Порушень із дією block: {integer.format(report.action_counts.block)}. Виправте дані й завантажте набір повторно.
          </p>
        </div>
      ) : null}

      <section className="qr-section" aria-labelledby="qr-violations-title">
        <div className="qr-section__head">
          <h2 id="qr-violations-title" className="qr-section__title">Порушення</h2>
          {selected ? (
            <button type="button" className="qr-link" onClick={() => setSelected(null)}>
              Показати всі
            </button>
          ) : null}
        </div>

        <div className="qr-actions" role="group" aria-label="Фільтр за дією">
          {ACTIONS.map((action) => (
            <ActionCard
              key={action}
              action={action}
              count={report.action_counts[action]}
              selected={selected === action}
              onToggle={() => setSelected(selected === action ? null : action)}
            />
          ))}
        </div>
        <p className="qr-note">block не знижує Quality Score, а блокує публікацію набору.</p>

        <p className="qr-sr-only" aria-live="polite">
          Показано {visible.length} з {report.violations.length} правил із порушеннями
        </p>

        {report.violations.length === 0 ? (
          <EmptyState title="Порушень немає" text="Усі рядки пройшли перевірку за правилами набору." />
        ) : visible.length === 0 ? (
          <EmptyState title={`Порушень із дією ${selected} немає`} text="Оберіть іншу дію або покажіть усі порушення." />
        ) : (
          <ViolationsTable violations={visible} />
        )}
      </section>

      <section className="qr-section" aria-labelledby="qr-rules-title">
        <div className="qr-section__head">
          <h2 id="qr-rules-title" className="qr-section__title">Правила набору</h2>
          <span className="qr-muted">Правил: {integer.format(rules.length)}</span>
        </div>
        {rules.length === 0 ? (
          <EmptyState title="Правила не задані" text="Для цього набору ще немає правил якості." />
        ) : (
          <RulesTable rules={rules} />
        )}
      </section>
    </>
  )
}

function LoadingState() {
  return (
    <div className="qr-loading" aria-busy="true" aria-live="polite">
      <span className="qr-sr-only">Завантаження правил і порушень…</span>
      <div className="qr-stats">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="qr-skeleton qr-skeleton--card" />
        ))}
      </div>
      <div className="qr-skeleton qr-skeleton--table" />
      <div className="qr-skeleton qr-skeleton--table" />
    </div>
  )
}

function ErrorState({ httpStatus, onRetry }: { httpStatus?: number; onRetry: () => void }) {
  const { title, text, retry } = describeError(httpStatus)
  return (
    <div className="qr-error" role="alert">
      <p className="qr-error__title">{title}</p>
      <p className="qr-error__text">{text}</p>
      {retry ? (
        <button type="button" className="qr-btn qr-btn--primary" onClick={onRetry}>
          Повторити
        </button>
      ) : null}
    </div>
  )
}

export default function QualityRulesPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [state, reload] = useQualityData(id)

  return (
    <div className="qr-page">
      <header className="qr-header">
        <div>
          <h1 className="qr-title">Правила якості</h1>
          <p className="qr-subtitle">Набір №{id}: правила та порушення</p>
        </div>
        <button type="button" className="qr-btn qr-btn--secondary" onClick={() => navigate(-1)}>
          Назад
        </button>
      </header>

      {state.status === 'loading' ? <LoadingState /> : null}
      {state.status === 'error' ? <ErrorState httpStatus={state.httpStatus} onRetry={reload} /> : null}
      {state.status === 'success' ? <Report rules={state.rules} report={state.report} /> : null}
    </div>
  )
}
