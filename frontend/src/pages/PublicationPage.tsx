import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchDatasets } from '../api/datasets'
import {
  applyAnonymization,
  checkPublication,
  fetchDatasetVersions,
  previewAnonymization,
  publishDataset,
} from '../api/publication'
import { fetchPiiScan } from '../api/datasets'
import type {
  AnonymizationMethodName,
  AnonymizationPreview,
  AnonymizedVersion,
  DatasetVersion,
  DatasetVersionInfo,
  PublicationCheck,
  PublishResult,
} from '../api/types'
import { LegalBasisPanel } from '../components/LegalBasisPanel'
import { ErrorMessage } from '../components/ErrorMessage'
import { ClassBadge, StatusBadge } from '../components/Badges'

const METHOD_LABELS: Record<AnonymizationMethodName, string> = {
  mask: 'Маскування (***)',
  generalize: 'Узагальнення',
  hmac: 'HMAC-псевдонімізація',
  redact: 'Видалення колонки',
}

const DEFAULT_METHODS: Record<string, AnonymizationMethodName> = {
  person_name: 'mask',
  address: 'mask',
  email: 'mask',
  phone: 'mask',
  birth_date: 'generalize',
  ipn: 'hmac',
  passport: 'hmac',
  iban: 'hmac',
  card: 'hmac',
}

const defaultRetention = () => {
  const date = new Date()
  date.setDate(date.getDate() + 180)
  return date.toISOString().slice(0, 10)
}

const today = () => new Date().toISOString().slice(0, 10)

const integer = new Intl.NumberFormat('uk-UA')

const formatDateTime = (iso: string) => new Date(iso).toLocaleString('uk-UA')

export default function PublicationPage() {
  const { id } = useParams<{ id: string }>()
  const datasetId = id ?? ''

  const [dataset, setDataset] = useState<DatasetVersion | null>(null)
  const [findings, setFindings] = useState<{ column_name: string; pii_type: string | null }[]>([])
  const [methods, setMethods] = useState<Record<string, AnonymizationMethodName>>({})
  const [versions, setVersions] = useState<DatasetVersionInfo[]>([])
  const [preview, setPreview] = useState<AnonymizationPreview | null>(null)
  const [applied, setApplied] = useState<AnonymizedVersion | null>(null)
  const [gate, setGate] = useState<PublicationCheck | null>(null)
  const [published, setPublished] = useState<PublishResult | null>(null)
  const [retention, setRetention] = useState(defaultRetention())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState<'preview' | 'apply' | 'gate' | 'publish' | null>(null)

  const refreshVersions = () =>
    fetchDatasetVersions(datasetId).then(setVersions)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    const [scanResult, versionsResult, datasetsResult] = await Promise.allSettled([
      fetchPiiScan(datasetId),
      fetchDatasetVersions(datasetId),
      fetchDatasets(),
    ])

    if (versionsResult.status === 'rejected') {
      setError(
        versionsResult.reason instanceof Error
          ? versionsResult.reason.message
          : 'Не вдалося завантажити версії набору',
      )
    } else {
      setVersions(versionsResult.value)
    }

    if (scanResult.status === 'fulfilled') {
      const active = scanResult.value.findings.filter(
        (finding) => finding.user_confirmed !== false && finding.pii_type,
      )
      setFindings(active)
      setMethods(() => {
        const next: Record<string, AnonymizationMethodName> = {}
        for (const finding of active) {
          next[finding.column_name] =
            DEFAULT_METHODS[finding.pii_type ?? ''] ?? 'mask'
        }
        return next
      })
    }

    if (datasetsResult.status === 'fulfilled') {
      setDataset(
        datasetsResult.value.find((item) => item.dataset_id === Number(datasetId)) ?? null,
      )
    }

    setLoading(false)
  }, [datasetId])

  useEffect(() => {
    load()
  }, [load])

  const estimatedClass = useMemo(() => {
    if (Object.values(methods).includes('hmac')) return 'Personal'
    return findings.length > 0 ? 'Confidential' : 'Internal'
  }, [methods, findings])

  const runPreview = async () => {
    setBusy('preview')
    setError(null)
    setNotice(null)
    try {
      const result = await previewAnonymization(datasetId, methods)
      setPreview(result)
      setNotice('Попередній перегляд готовий. Файл і версія ще не створені.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося побудувати попередній перегляд')
    } finally {
      setBusy(null)
    }
  }

  const runApply = async () => {
    setBusy('apply')
    setError(null)
    setNotice(null)
    try {
      const result = await applyAnonymization(datasetId, methods)
      setApplied(result)
      setPreview(null)
      setNotice(
        `Створено очищену версію v${result.version_number} (${result.file_name}). SHA-256: ${result.sha256.slice(0, 16)}…`,
      )
      await refreshVersions()
      setGate(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося застосувати анонімізацію')
    } finally {
      setBusy(null)
    }
  }

  const runGate = async () => {
    setBusy('gate')
    setError(null)
    setNotice(null)
    try {
      const result = await checkPublication(datasetId, retention || undefined)
      setGate(result)
      setNotice(
        result.allowed
          ? 'Перевірку пройдено: набір можна публікувати.'
          : 'Публікацію заблоковано. Усуньте причини нижче.',
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося перевірити готовність')
    } finally {
      setBusy(null)
    }
  }

  const runPublish = async () => {
    setBusy('publish')
    setError(null)
    setNotice(null)
    try {
      const result = await publishDataset(datasetId, retention)
      setPublished(result)
      setGate(result.gate)
      setDataset((prev) =>
        prev
          ? {
              ...prev,
              status: 'Published',
              data_class: result.data_class,
              updated_at: result.published_at,
            }
          : prev,
      )
      setNotice('Набір опубліковано. Він з’явився в каталозі для Data Consumer.')
      await refreshVersions()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося опублікувати набір')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="qr-page">
      <div className="page-header page-header--row">
        <div className="page-header">
          <h1>Публікація набору</h1>
          <p className="subtitle">
            Набір №{datasetId}
            {dataset ? ` · ${dataset.file_name}` : ''}: анонімізація PII, перевірка gate і
            публікація в каталозі.
          </p>
          {dataset && (
            <div className="actions">
              <ClassBadge value={dataset.data_class} />
              <StatusBadge value={dataset.status} />
            </div>
          )}
        </div>
        <div className="actions">
          <Link to={`/datasets/${datasetId}/legal`} className="btn btn--secondary">
            Правові підстави
          </Link>
          <Link to="/datasets" className="btn btn--secondary">
            До наборів
          </Link>
        </div>
      </div>

      {notice && (
        <div className="alert alert--success" role="status">
          <div className="alert__body">
            <span className="alert__title">Статус</span>
            <span>{notice}</span>
          </div>
        </div>
      )}
      {error && <ErrorMessage title="Не вдалося виконати дію">{error}</ErrorMessage>}
      {loading && <p className="subtitle">Завантаження…</p>}

      <section className="card" aria-labelledby="anonymize-title">
        <div className="page-header page-header--row">
          <div className="page-header">
            <h2 id="anonymize-title">Анонімізація PII</h2>
            <p className="subtitle">
              Спочатку перегляньте результат без запису, потім застосуйте — буде створено
              незмінну очищену версію. HMAC потребує активної правової підстави.
            </p>
          </div>
          <span className="badge badge--quality-medium">Очікуваний клас: {estimatedClass}</span>
        </div>

        {findings.length === 0 ? (
          <p className="cell-muted">PII-колонок не виявлено — анонімізація не потрібна.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Колонка</th>
                  <th scope="col">Тип PII</th>
                  <th scope="col">Метод</th>
                </tr>
              </thead>
              <tbody>
                {findings.map((finding) => (
                  <tr key={finding.column_name}>
                    <td className="cell-strong">{finding.column_name}</td>
                    <td>{finding.pii_type}</td>
                    <td>
                      <select
                        className="filter-select"
                        aria-label={`Метод для ${finding.column_name}`}
                        value={methods[finding.column_name] ?? 'mask'}
                        onChange={(event) =>
                          setMethods((prev) => ({
                            ...prev,
                            [finding.column_name]: event.target.value as AnonymizationMethodName,
                          }))
                        }
                      >
                        {(Object.keys(METHOD_LABELS) as AnonymizationMethodName[]).map((method) => (
                          <option key={method} value={method}>
                            {METHOD_LABELS[method]}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="actions">
          <button
            type="button"
            className="btn btn--secondary"
            onClick={runPreview}
            disabled={busy !== null}
          >
            {busy === 'preview' ? 'Перевірка…' : 'Попередній перегляд'}
          </button>
          <button type="button" className="btn" onClick={runApply} disabled={busy !== null}>
            {busy === 'apply' ? 'Застосування…' : 'Застосувати анонімізацію'}
          </button>
        </div>

        {preview && (
          <div className="alert alert--info" role="status">
            <div className="alert__body">
              <span className="alert__title">Попередній перегляд</span>
              <span>
                Колонок PII: {preview.pii_columns_count}; очікуваний клас:{' '}
                {preview.estimated_class}; методи:{' '}
                {preview.columns
                  .map((column) => `${column.column_name} → ${column.method}`)
                  .join(', ')}
              </span>
            </div>
          </div>
        )}
        {applied && (
          <div className="alert alert--success" role="status">
            <div className="alert__body">
              <span className="alert__title">Очищену версію створено</span>
              <span>
                v{applied.version_number}, рядків: {integer.format(applied.row_count)}, клас:{' '}
                {applied.data_class}
              </span>
            </div>
          </div>
        )}
      </section>

      <section className="card" aria-labelledby="gate-title">
        <div className="page-header page-header--row">
          <div className="page-header">
            <h2 id="gate-title">Publication gate</h2>
            <p className="subtitle">
              Перевірка є лише читанням. Публікація змінює статус і клас набору та фіксується в
              аудиті.
            </p>
          </div>
          <label className="filter-select-label" htmlFor="retention">
            <span>Зберігати до:</span>
            <input
              id="retention"
              type="date"
              className="filter-select"
              min={today()}
              value={retention}
              onChange={(event) => {
                setRetention(event.target.value)
                setGate(null)
              }}
            />
          </label>
        </div>

        <div className="actions">
          <button
            type="button"
            className="btn btn--secondary"
            onClick={runGate}
            disabled={busy !== null}
          >
            {busy === 'gate' ? 'Перевірка…' : 'Перевірити готовність'}
          </button>
          <button
            type="button"
            className="btn"
            onClick={runPublish}
            disabled={busy !== null || !gate?.allowed || dataset?.status === 'Published'}
          >
            {busy === 'publish' ? 'Публікація…' : 'Опублікувати'}
          </button>
        </div>

        {gate && (
          <div className={gate.allowed ? 'alert alert--success' : 'alert alert--warning'} role="status">
            <div className="alert__body">
              <span className="alert__title">
                {gate.allowed ? 'Публікацію дозволено' : 'Публікацію заблоковано'}
              </span>
              <span>
                Новий клас: {gate.new_class}. Clean-версія:{' '}
                {gate.clean_version_id ?? 'відсутня'}.
              </span>
              {!gate.allowed && (
                <ul>
                  {gate.reasons.map((reason) => (
                    <li key={reason.code}>
                      <code>{reason.code}</code>: {reason.message}
                      {reason.columns?.length ? ` (${reason.columns.join(', ')})` : ''}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        {published && (
          <div className="alert alert--success" role="status">
            <div className="alert__body">
              <span className="alert__title">Опубліковано</span>
              <span>
                Клас: {published.data_class}; зберігати до: {published.retention_until}; автор:{' '}
                {published.published_by}.
              </span>
            </div>
          </div>
        )}
      </section>

      <section className="card card--table-section" aria-labelledby="versions-title">
        <div className="page-header" style={{ padding: 'var(--space-5) var(--space-5) 0' }}>
          <h2 id="versions-title">Версії набору</h2>
          <p className="subtitle">Оригінальні та очищені версії; завантажується лише clean.</p>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">ID</th>
                <th scope="col">Тип</th>
                <th scope="col">Версія</th>
                <th scope="col">Файл</th>
                <th scope="col">Рядків</th>
                <th scope="col">Клас</th>
                <th scope="col">SHA-256</th>
                <th scope="col">Створено</th>
              </tr>
            </thead>
            <tbody>
              {versions.length === 0 ? (
                <tr>
                  <td className="table__empty" colSpan={8}>
                    Версій ще немає
                  </td>
                </tr>
              ) : (
                versions.map((version) => (
                  <tr key={version.id}>
                    <td className="cell-muted">{version.id}</td>
                    <td>{version.kind === 'clean' ? 'Очищена' : 'Оригінал'}</td>
                    <td>v{version.version_number}</td>
                    <td>{version.file_name}</td>
                    <td>{integer.format(version.row_count)}</td>
                    <td>{version.data_class ?? '—'}</td>
                    <td>
                      <code className="qr-code">{version.sha256.slice(0, 12)}…</code>
                    </td>
                    <td className="cell-muted">{formatDateTime(version.created_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <LegalBasisPanel datasetId={datasetId} />
    </div>
  )
}
