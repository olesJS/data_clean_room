import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  createLegalBasis,
  fetchLegalBasis,
  revokeLegalBasis,
} from '../api/exchange'
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
            Для публікації набору з псевдонімізованими колонками (HMAC) потрібна зареєстрована чинна правова підстава. Без правової підстави запити на цей набір не можна буде схвалити.
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

      <div className="stats" style={{ margin: 'var(--space-4) 0' }}>
        <div className="stat">
          <span className="stat__label">Усього підстав</span>
          <span className="stat__value">{stats.total}</span>
        </div>
        <div className="stat">
          <span className="stat__label">Чинні (активні)</span>
          <span className="stat__value stat__value--ok">{stats.active}</span>
        </div>
        <div className="stat">
          <span className="stat__label">Відкликані</span>
          <span className="stat__value stat__value--warn">{stats.revoked}</span>
        </div>
      </div>

      {notice && (
        <div className="alert alert--success" role="status" style={{ marginBottom: 'var(--space-3)' }}>
          <IconCheck size={16} />
          <div className="alert__body">
            <span className="alert__title">Успішно</span>
            <span>{notice}</span>
          </div>
        </div>
      )}

      {error && (
        <div style={{ marginBottom: 'var(--space-3)' }}>
          <ErrorMessage title="Помилка операції з правовими підставами">{error}</ErrorMessage>
        </div>
      )}

      {/* Форма реєстрації нової правової підстави */}
      {showForm && (
        <div className="card legal-basis-form-card" style={{ background: 'var(--color-light)', marginBottom: 'var(--space-4)', border: '1px solid var(--color-line)' }}>
          <div className="page-header page-header--row">
            <div>
              <h3>Реєстрація нової правової підстави</h3>
              <p className="subtitle">
                Вкажіть підставу для обробки персональних даних (GDPR Art. 6 / Закон України про захист персональних даних).
              </p>
            </div>
            <button
              type="button"
              className="btn-icon"
              onClick={() => setShowForm(false)}
              aria-label="Закрити форму"
            >
              <IconX size={18} />
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-3)', margin: 'var(--space-3) 0' }}>
            <label className="field-label">
              <span className="field-label__text">Тип правової підстави (type):</span>
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

          <div style={{ display: 'flex', gap: 'var(--space-3)', marginTop: 'var(--space-3)' }}>
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

      {/* Модальний діалог відкликання правової підстави / згоди */}
      {revoking && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="revoke-modal-title">
          <div className="modal-dialog card" style={{ maxWidth: '500px', borderColor: 'var(--color-danger)' }}>
            <div className="page-header" style={{ marginBottom: 'var(--space-3)' }}>
              <h3 id="revoke-modal-title" style={{ color: 'var(--danger-text)', margin: 0 }}>
                Відкликати {revoking.type === 'consent' ? 'згоду' : 'правову підставу'}?
              </h3>
              <p className="subtitle" style={{ marginTop: '4px' }}>
                Документ: <strong>{revoking.document_ref}</strong>. Відкликання є незворотним. Будь-які запити на обмін даними за цією підставою буде заблоковано.
              </p>
            </div>

            <label className="field-label" style={{ marginBottom: 'var(--space-4)', display: 'block' }}>
              <span className="field-label__text">Причина відкликання *:</span>
              <textarea
                className="filter-select"
                style={{ width: '100%', minHeight: '80px', padding: '8px', fontSize: '14px', resize: 'vertical' }}
                maxLength={500}
                placeholder="Вкажіть причину відкликання (напр. Суб’єкт відкликав згоду на обробку ПД)"
                value={revokeReason}
                onChange={(e) => setRevokeReason(e.target.value)}
                required
              />
            </label>

            <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'flex-end' }}>
              <Button
                variant="secondary"
                onClick={() => setRevoking(null)}
                disabled={revokeSubmitting}
              >
                Скасувати
              </Button>
              <button
                type="button"
                className="btn btn--danger"
                style={{ background: 'var(--color-danger)', color: '#fff' }}
                onClick={submitRevoke}
                disabled={revokeSubmitting || revokeReason.trim().length === 0}
              >
                {revokeSubmitting ? 'Відкликання…' : 'Підтвердити відкликання'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Список правових підстав */}
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
                  Правових підстав для цього набору ще не додано. Без правової підстави запити на цей набір не можна буде схвалити.
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
                          {basis.revoked_reason || 'Відкликано'}
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="btn btn--danger-soft btn--sm"
                          onClick={() => {
                            setRevoking(basis)
                            setRevokeReason('')
                            setNotice(null)
                            setError(null)
                          }}
                          title={basis.type === 'consent' ? 'Відкликати згоду' : 'Відкликати правову підставу'}
                        >
                          {basis.type === 'consent' ? 'Відкликати згоду' : 'Відкликати'}
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

      <div className="card__footer" style={{ marginTop: 'var(--space-3)' }}>
        <span className="caption cell-muted">
          <IconInfo size={14} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '4px' }} />
          Відкликання згоди діє негайно. Будь-які запити на обмін або завантаження цього набору даних блокуватимуться кодом 409/403.
        </span>
      </div>
    </section>
  )
}
