import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  createLegalBasis,
  fetchLegalBasis,
  revokeLegalBasis,
} from '../api/publication'
import {
  LEGAL_BASIS_PURPOSE_LABELS,
  LEGAL_BASIS_TYPE_LABELS,
  type LegalBasis,
  type LegalBasisPurpose,
  type LegalBasisType,
} from '../api/types'
import { Button } from './Button'
import { ErrorMessage } from './ErrorMessage'
import { IconCheck, IconInfo, IconRefresh, IconShield, IconX } from './icons'

const TYPES: LegalBasisType[] = ['consent', 'contract', 'law']
const PURPOSES: LegalBasisPurpose[] = ['analytics', 'research', 'reporting', 'publication']

const today = () => new Date().toISOString().slice(0, 10)

const formatDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString('uk-UA') : '—'

const formatDateTime = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString('uk-UA') : '—'

function basisStatus(basis: LegalBasis): { label: string; tone: string } {
  if (basis.revoked_at) return { label: 'Відкликано', tone: 'badge--expired' }
  if (!basis.is_active) return { label: 'Термін минув', tone: 'badge--expired' }
  return { label: 'Активна', tone: 'badge--published' }
}

interface LegalBasisPanelProps {
  datasetId: number | string
  onChanged?: () => void
}

export function LegalBasisPanel({ datasetId, onChanged }: LegalBasisPanelProps) {
  const [bases, setBases] = useState<LegalBasis[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [revoking, setRevoking] = useState<LegalBasis | null>(null)
  const [revokeReason, setRevokeReason] = useState('')
  const [revokeSubmitting, setRevokeSubmitting] = useState(false)

  const [type, setType] = useState<LegalBasisType>('consent')
  const [purpose, setPurpose] = useState<LegalBasisPurpose>('analytics')
  const [documentRef, setDocumentRef] = useState('')
  const [effectiveDate, setEffectiveDate] = useState(today())
  const [validUntil, setValidUntil] = useState('')

  const load = useCallback(() => {
    setError(null)
    fetchLegalBasis(datasetId)
      .then((data) => {
        setBases(data)
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : 'Не вдалося завантажити правові підстави'),
      )
  }, [datasetId])

  useEffect(() => {
    load()
  }, [load])

  const stats = useMemo(() => {
    const list = bases ?? []
    return {
      total: list.length,
      active: list.filter((basis) => basis.is_active && !basis.revoked_at).length,
      revoked: list.filter((basis) => basis.revoked_at).length,
    }
  }, [bases])

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    setNotice(null)
    try {
      const created = await createLegalBasis(datasetId, {
        type,
        purpose,
        document_ref: documentRef.trim(),
        date: effectiveDate,
        valid_until: validUntil || null,
      })
      setBases((prev) => [created, ...(prev ?? [])])
      setNotice('Правову підставу зареєстровано успішно.')
      setShowForm(false)
      setDocumentRef('')
      setValidUntil('')
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося створити правову підставу')
    } finally {
      setSubmitting(false)
    }
  }

  const submitRevoke = async () => {
    if (!revoking) return
    setRevokeSubmitting(true)
    setError(null)
    setNotice(null)
    try {
      const updated = await revokeLegalBasis(revoking.id, revokeReason.trim())
      setBases((prev) =>
        (prev ?? []).map((basis) => (basis.id === updated.id ? updated : basis)),
      )
      setNotice('Правову підставу відкликано. Нові схвалення або передача даних за нею блокуватимуться.')
      setRevoking(null)
      setRevokeReason('')
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося відкликати правову підставу')
    } finally {
      setRevokeSubmitting(false)
    }
  }

  const canSubmit = documentRef.trim().length > 0 && effectiveDate.length > 0

  return (
    <section className="card legal-basis-card" aria-labelledby="legal-basis-title">
      <div className="page-header page-header--row">
        <div>
          <h2 id="legal-basis-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <IconShield size={20} />
            <span>Правові підстави (Legal Basis)</span>
          </h2>
          <p className="subtitle">
            Для публікації набору з псевдонімізованими колонками (HMAC) потрібна зареєстрована чинна правова підстава.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button
            variant="secondary"
            onClick={load}
            title="Оновити список правових підстав"
          >
            <IconRefresh size={16} />
            <span>Оновити</span>
          </Button>
          {!showForm && (
            <Button
              variant="primary"
              onClick={() => {
                setShowForm(true)
                setNotice(null)
                setError(null)
              }}
            >
              <span>+ Додати підставу</span>
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: 'var(--space-4)' }}>
          <ErrorMessage title="Помилка роботи з правовими підставами">{error}</ErrorMessage>
        </div>
      )}

      {notice && (
        <div className="alert alert--info" style={{ marginBottom: 'var(--space-4)' }}>
          <IconInfo size={16} />
          <div className="alert__body">
            <span className="alert__title">Інформація</span>
            <span>{notice}</span>
          </div>
        </div>
      )}

      <div className="legal-basis-stats" style={{ display: 'flex', gap: 'var(--space-4)', marginBottom: 'var(--space-4)', flexWrap: 'wrap' }}>
        <span className="badge badge--quality-medium">
          Всього підстав: {stats.total}
        </span>
        <span className={`badge ${stats.active > 0 ? 'badge--published' : 'badge--warning'}`}>
          <IconCheck size={12} />
          <span>Активних: {stats.active}</span>
        </span>
        {stats.revoked > 0 && (
          <span className="badge badge--expired">
            <IconX size={12} />
            <span>Відкликаних: {stats.revoked}</span>
          </span>
        )}
      </div>

      {/* Форма створення нової правової підстави */}
      {showForm && (
        <div className="card form-card" style={{ background: 'var(--color-light)', marginBottom: 'var(--space-4)', border: '1px solid var(--color-line)' }}>
          <div className="page-header">
            <h3>Реєстрація нової правової підстави</h3>
            <p className="subtitle">
              Вкажіть юридичну підставу (згода суб'єкта, договір, норма закону) для обробки та передачі даних.
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
            <label className="field-label">
              <span className="field-label__text">Тип підстави:</span>
              <select
                className="filter-select method-select"
                value={type}
                onChange={(e) => setType(e.target.value as LegalBasisType)}
              >
                {TYPES.map((t) => (
                  <option key={t} value={t}>
                    {LEGAL_BASIS_TYPE_LABELS[t]}
                  </option>
                ))}
              </select>
            </label>

            <label className="field-label">
              <span className="field-label__text">Мета обробки (purpose):</span>
              <select
                className="filter-select method-select"
                value={purpose}
                onChange={(e) => setPurpose(e.target.value as LegalBasisPurpose)}
              >
                {PURPOSES.map((p) => (
                  <option key={p} value={p}>
                    {LEGAL_BASIS_PURPOSE_LABELS[p]}
                  </option>
                ))}
              </select>
            </label>

            <label className="field-label">
              <span className="field-label__text">Номер / реквізити документа *:</span>
              <input
                type="text"
                className="filter-select"
                placeholder="напр. Договір №124-П або Згода №4"
                value={documentRef}
                onChange={(e) => setDocumentRef(e.target.value)}
                required
              />
            </label>

            <label className="field-label">
              <span className="field-label__text">Дата набуття чинності *:</span>
              <input
                type="date"
                className="filter-select"
                value={effectiveDate}
                onChange={(e) => setEffectiveDate(e.target.value)}
                required
              />
            </label>

            <label className="field-label">
              <span className="field-label__text">Діє до (необов'язково):</span>
              <input
                type="date"
                className="filter-select"
                value={validUntil}
                min={effectiveDate}
                onChange={(e) => setValidUntil(e.target.value)}
              />
            </label>
          </div>

          <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
            <Button
              variant="primary"
              onClick={submit}
              disabled={submitting || !canSubmit}
            >
              {submitting ? 'Збереження…' : 'Зареєструвати підставу'}
            </Button>
            <Button
              variant="secondary"
              onClick={() => setShowForm(false)}
              disabled={submitting}
            >
              Скасувати
            </Button>
          </div>
        </div>
      )}

      {/* Діалог відкликання правової підстави */}
      {revoking && (
        <div className="card revoke-card" style={{ background: 'var(--danger-soft)', borderColor: 'var(--color-danger)', marginBottom: 'var(--space-4)' }}>
          <div className="page-header">
            <h3 style={{ color: 'var(--danger-text)' }}>Відкликання правової підстави</h3>
            <p className="subtitle" style={{ color: 'var(--danger-text)' }}>
              Документ: <strong>{revoking.document_ref}</strong>. Відкликання є незворотним і діє негайно.
            </p>
          </div>

          <label className="field-label" style={{ marginBottom: 'var(--space-3)', display: 'block' }}>
            <span className="field-label__text">Причина відкликання *:</span>
            <input
              type="text"
              className="filter-select"
              style={{ width: '100%', maxWidth: '480px' }}
              maxLength={500}
              placeholder="напр. Суб’єкт відкликав згоду / закінчився строк контракту"
              value={revokeReason}
              onChange={(e) => setRevokeReason(e.target.value)}
            />
          </label>

          <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
            <button
              type="button"
              className="btn btn--danger"
              style={{ background: 'var(--color-danger)', color: '#fff' }}
              onClick={submitRevoke}
              disabled={revokeSubmitting || revokeReason.trim().length === 0}
            >
              {revokeSubmitting ? 'Відкликання…' : 'Підтвердити відкликання'}
            </button>
            <Button
              variant="secondary"
              onClick={() => setRevoking(null)}
              disabled={revokeSubmitting}
            >
              Скасувати
            </Button>
          </div>
        </div>
      )}

      {/* Список правових підстав */}
      {bases === null && !error ? (
        <p className="cell-muted">Завантаження правових підстав…</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Тип</th>
                <th scope="col">Мета</th>
                <th scope="col">Документ</th>
                <th scope="col">Дата</th>
                <th scope="col">Діє до</th>
                <th scope="col">Статус</th>
                <th scope="col">Відкликано</th>
                <th scope="col">Дії</th>
              </tr>
            </thead>
            <tbody>
              {bases && bases.length === 0 ? (
                <tr>
                  <td className="table__empty" colSpan={8}>
                    Правових підстав для цього набору ще не додано.
                  </td>
                </tr>
              ) : (
                bases?.map((basis) => {
                  const status = basisStatus(basis)
                  return (
                    <tr key={basis.id}>
                      <td className="cell-strong">{LEGAL_BASIS_TYPE_LABELS[basis.type] ?? basis.type}</td>
                      <td>{LEGAL_BASIS_PURPOSE_LABELS[basis.purpose] ?? basis.purpose}</td>
                      <td>{basis.document_ref}</td>
                      <td className="cell-muted">{formatDate(basis.date)}</td>
                      <td className="cell-muted">{formatDate(basis.valid_until)}</td>
                      <td>
                        <span className={`badge ${status.tone}`}>
                          {status.label}
                        </span>
                      </td>
                      <td className="cell-muted">
                        {basis.revoked_at ? formatDateTime(basis.revoked_at) : '—'}
                      </td>
                      <td>
                        {basis.revoked_at ? (
                          <span className="cell-muted" style={{ fontSize: '12px' }}>
                            {basis.revoked_reason || '—'}
                          </span>
                        ) : (
                          <button
                            type="button"
                            className="btn btn--sm"
                            style={{ borderColor: 'var(--color-danger)', color: 'var(--color-danger)' }}
                            onClick={() => {
                              setRevoking(basis)
                              setRevokeReason('')
                              setNotice(null)
                              setError(null)
                            }}
                          >
                            Відкликати
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
