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
import { ErrorMessage } from './ErrorMessage'

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

export function LegalBasisPanel({ datasetId }: { datasetId: number | string }) {
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
      .then(setBases)
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
      active: list.filter((basis) => basis.is_active).length,
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
      setNotice('Правову підставу зареєстровано. Подія CREATE_LEGAL_BASIS записана в аудит.')
      setShowForm(false)
      setDocumentRef('')
      setValidUntil('')
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
      setNotice(
        'Правову підставу відкликано. Нові запити на доступ і завантаження за нею будуть відхилені.',
      )
      setRevoking(null)
      setRevokeReason('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося відкликати правову підставу')
    } finally {
      setRevokeSubmitting(false)
    }
  }

  const canSubmit = documentRef.trim().length > 0 && effectiveDate.length > 0

  return (
    <section className="card" aria-labelledby="legal-basis-title">
      <div className="page-header page-header--row">
        <div className="page-header">
          <h2 id="legal-basis-title">Правові підстави</h2>
          <p className="subtitle">
            Активна підстава з потрібною метою дозволяє передачу очищеного набору. Відкликання
            діє негайно.
          </p>
        </div>
        <button
          type="button"
          className="btn btn--secondary btn--sm"
          onClick={() => setShowForm((value) => !value)}
        >
          {showForm ? 'Закрити форму' : 'Додати підставу'}
        </button>
      </div>

      <div className="stats">
        <div className="stat">
          <span className="stat__label">Усього записів</span>
          <span className="stat__value">{stats.total}</span>
        </div>
        <div className="stat">
          <span className="stat__label">Активних</span>
          <span className="stat__value stat__value--ok">{stats.active}</span>
        </div>
        <div className="stat">
          <span className="stat__label">Відкликано</span>
          <span className="stat__value stat__value--warn">{stats.revoked}</span>
        </div>
      </div>

      {notice && (
        <div className="alert alert--success" role="status">
          <div className="alert__body">
            <span className="alert__title">Готово</span>
            <span>{notice}</span>
          </div>
        </div>
      )}
      {error && <ErrorMessage title="Не вдалося виконати дію">{error}</ErrorMessage>}

      {showForm && (
        <div className="card">
          <div className="page-header">
            <h3>Нова правова підстава</h3>
          </div>
          <div className="actions">
            <label className="filter-select-label" htmlFor="basis-type">
              <span>Тип:</span>
              <select
                id="basis-type"
                className="filter-select"
                value={type}
                onChange={(event) => setType(event.target.value as LegalBasisType)}
              >
                {TYPES.map((value) => (
                  <option key={value} value={value}>
                    {LEGAL_BASIS_TYPE_LABELS[value]}
                  </option>
                ))}
              </select>
            </label>
            <label className="filter-select-label" htmlFor="basis-purpose">
              <span>Мета:</span>
              <select
                id="basis-purpose"
                className="filter-select"
                value={purpose}
                onChange={(event) => setPurpose(event.target.value as LegalBasisPurpose)}
              >
                {PURPOSES.map((value) => (
                  <option key={value} value={value}>
                    {LEGAL_BASIS_PURPOSE_LABELS[value]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="filter-select-label" htmlFor="basis-document">
            <span>Документ / реквізит:</span>
            <input
              id="basis-document"
              type="text"
              className="filter-select"
              maxLength={255}
              value={documentRef}
              onChange={(event) => setDocumentRef(event.target.value)}
              placeholder="Наприклад: CONSENT-2026-001"
            />
          </label>
          <div className="actions">
            <label className="filter-select-label" htmlFor="basis-date">
              <span>Дата:</span>
              <input
                id="basis-date"
                type="date"
                className="filter-select"
                value={effectiveDate}
                onChange={(event) => setEffectiveDate(event.target.value)}
              />
            </label>
            <label className="filter-select-label" htmlFor="basis-valid">
              <span>Діє до (необов’язково):</span>
              <input
                id="basis-valid"
                type="date"
                className="filter-select"
                min={today()}
                value={validUntil}
                onChange={(event) => setValidUntil(event.target.value)}
              />
            </label>
          </div>
          <div className="actions">
            <button type="button" className="btn" onClick={submit} disabled={submitting || !canSubmit}>
              {submitting ? 'Збереження…' : 'Зареєструвати'}
            </button>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => setShowForm(false)}
              disabled={submitting}
            >
              Скасувати
            </button>
          </div>
        </div>
      )}

      {revoking && (
        <div className="card" aria-labelledby="revoke-title">
          <div className="page-header">
            <h3 id="revoke-title">Відкликати правову підставу</h3>
            <p className="subtitle">
              Документ: {revoking.document_ref}. Відкликання незворотне.
            </p>
          </div>
          <label className="filter-select-label" htmlFor="revoke-reason">
            <span>Причина:</span>
            <input
              id="revoke-reason"
              type="text"
              className="filter-select"
              maxLength={500}
              value={revokeReason}
              onChange={(event) => setRevokeReason(event.target.value)}
              placeholder="Наприклад: суб’єкт відкликав згоду"
            />
          </label>
          <div className="actions">
            <button
              type="button"
              className="btn btn--danger-soft"
              onClick={submitRevoke}
              disabled={revokeSubmitting || revokeReason.trim().length === 0}
            >
              {revokeSubmitting ? 'Відкликання…' : 'Підтвердити відкликання'}
            </button>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => setRevoking(null)}
              disabled={revokeSubmitting}
            >
              Скасувати
            </button>
          </div>
        </div>
      )}

      {bases === null && !error && <p className="subtitle">Завантаження…</p>}

      {bases !== null && (
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
              {bases.length === 0 ? (
                <tr>
                  <td className="table__empty" colSpan={8}>
                    Правових підстав ще немає
                  </td>
                </tr>
              ) : (
                bases.map((basis) => {
                  const status = basisStatus(basis)
                  return (
                    <tr key={basis.id}>
                      <td>{LEGAL_BASIS_TYPE_LABELS[basis.type] ?? basis.type}</td>
                      <td>{LEGAL_BASIS_PURPOSE_LABELS[basis.purpose] ?? basis.purpose}</td>
                      <td>{basis.document_ref}</td>
                      <td className="cell-muted">{formatDate(basis.date)}</td>
                      <td className="cell-muted">{formatDate(basis.valid_until)}</td>
                      <td>
                        <span className={`badge badge--status ${status.tone}`}>
                          <span className="badge__dot" aria-hidden="true" />
                          {status.label}
                        </span>
                      </td>
                      <td className="cell-muted">
                        {basis.revoked_at ? formatDateTime(basis.revoked_at) : '—'}
                      </td>
                      <td>
                        {basis.revoked_at ? (
                          <span className="cell-muted">{basis.revoked_reason || '—'}</span>
                        ) : (
                          <button
                            type="button"
                            className="btn btn--danger-soft"
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
