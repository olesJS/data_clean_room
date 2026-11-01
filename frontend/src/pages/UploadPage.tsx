import { useId, useMemo, useRef, useState, type DragEvent, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchDatasets, uploadDataset } from '../api/datasets'
import type { DatasetVersion, UploadResult } from '../api/types'
import { Alert } from '../components/Alert'
import { StatusBadge } from '../components/Badges'
import { Button } from '../components/Button'
import { Field } from '../components/Field'
import { IconCheckCircle, IconFile, IconLock, IconUpload } from '../components/icons'
import { PageHeader } from '../components/PageHeader'
import { MAX_UPLOAD_MB } from '../config'

type Stage = 'form' | 'uploading' | 'error' | 'success'
type Mode = 'new' | 'version'

const ALLOWED = ['.csv', '.json']
const extOf = (name: string) => name.slice(name.lastIndexOf('.')).toLowerCase()

/** Перевірка до надсилання (UC-02): формат, порожній файл, ліміт розміру. */
function validateFile(file: File): string | null {
  if (!ALLOWED.includes(extOf(file.name))) return 'Невірний формат файлу. Оберіть файл CSV або JSON.'
  if (file.size === 0) return 'Файл порожній. Оберіть файл із даними.'
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `Файл завеликий. Максимальний розмір — ${MAX_UPLOAD_MB} МБ.`
  return null
}

const formatSize = (bytes: number) =>
  bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} КБ` : `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} МБ`

export default function UploadPage() {
  const navigate = useNavigate()
  const selectId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [stage, setStage] = useState<Stage>('form')
  const [mode, setMode] = useState<Mode>('new')
  const [name, setName] = useState('')
  const [datasetId, setDatasetId] = useState('')
  const [datasets, setDatasets] = useState<DatasetVersion[] | null>(null)
  const [datasetsError, setDatasetsError] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [fileProblem, setFileProblem] = useState<string | null>(null)
  const [errors, setErrors] = useState<{ name?: string; dataset?: string; file?: string }>({})
  const [progress, setProgress] = useState(0)
  const [apiError, setApiError] = useState<string | null>(null)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [dragOver, setDragOver] = useState(false)

  // Існуючі набори для вибору «нова версія»: по одному на dataset_id.
  const options = useMemo(() => {
    const seen = new Map<number, string>()
    for (const d of datasets ?? []) if (!seen.has(d.dataset_id)) seen.set(d.dataset_id, d.dataset_name)
    return [...seen].map(([id, label]) => ({ id, label }))
  }, [datasets])

  const displayName = mode === 'version' ? (options.find((o) => String(o.id) === datasetId)?.label ?? name) : name.trim()
  const modeLabel = mode === 'version' ? 'Нова версія існуючого набору' : 'Новий набір'

  const loadDatasets = () => {
    setDatasetsError(null)
    fetchDatasets()
      .then(setDatasets)
      .catch((err: unknown) => setDatasetsError(err instanceof Error ? err.message : 'Не вдалося завантажити список наборів'))
  }

  const selectMode = (m: Mode) => {
    setMode(m)
    setErrors({})
    if (m === 'version') {
      if (!datasets) loadDatasets()
    } else {
      setDatasetId('')
    }
  }

  const selectDataset = (value: string) => {
    setDatasetId(value)
    setErrors((e) => ({ ...e, dataset: undefined }))
    const found = options.find((o) => String(o.id) === value)
    if (found) setName(found.label)
  }

  const clearInput = () => { if (inputRef.current) inputRef.current.value = '' }

  const pickFile = (f: File | undefined) => {
    if (!f) return
    const problem = validateFile(f)
    if (problem) {
      setFile(null)
      setFileProblem(problem)
      clearInput()
      return
    }
    setFileProblem(null)
    setFile(f)
    setStage('form')
    setApiError(null)
    setErrors((e) => ({ ...e, file: undefined }))
    if (mode === 'new' && !name.trim()) setName(f.name.replace(/\.[^.]+$/, ''))
  }

  const removeFile = () => { setFile(null); setFileProblem(null); clearInput() }

  const resetAll = () => {
    setStage('form'); setMode('new'); setName(''); setDatasetId(''); setFile(null); setFileProblem(null)
    setErrors({}); setProgress(0); setApiError(null); setResult(null); clearInput()
  }

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    pickFile(e.dataTransfer.files[0])
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const next: typeof errors = {}
    if (mode === 'new' && !name.trim()) next.name = 'Вкажіть назву набору'
    if (mode === 'version' && !datasetId) next.dataset = 'Оберіть існуючий набір'
    if (!file) next.file = 'Оберіть файл CSV або JSON'
    setErrors(next)
    if (Object.keys(next).length || !file) return

    setStage('uploading')
    setProgress(0)
    setApiError(null)
    try {
      const res = await uploadDataset({
        name: displayName,
        file,
        datasetId: mode === 'version' ? Number(datasetId) : undefined,
        onProgress: setProgress,
      })
      setResult(res)
      setStage('success')
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Не вдалося імпортувати файл.')
      setStage('error')
    }
  }

  const subtitle =
    stage === 'error' ? 'Файл не імпортовано.'
    : stage === 'success' ? 'Сира версія зберігається без змін, а подію записано в журнал аудиту'
    : 'Оберіть набір і файл. Формат та розмір перевіряються до надсилання.'

  const summary = (
    <div className="summary">
      <div>
        <p className="summary__title">{displayName}</p>
        <p className="summary__sub">{modeLabel}</p>
      </div>
      {stage === 'uploading' && <IconLock />}
    </div>
  )

  const fileMeta = file && `${formatSize(file.size)}${stage === 'uploading' ? ` · ${progress}%` : ` · ${extOf(file.name).slice(1).toUpperCase()}`}`

  return (
    <>
      <PageHeader title="Імпорт даних" subtitle={subtitle} />
      <input ref={inputRef} type="file" accept=".csv,.json" hidden onChange={(e) => pickFile(e.target.files?.[0])} />

      {stage === 'form' && (
        <form className="upload" onSubmit={handleSubmit} noValidate>
          <section className="card">
            <h3>Відомості про набір даних</h3>
            <Field label="Назва набору *" placeholder="Введіть назву набору даних" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} disabled={mode === 'version'} />
            <fieldset className="radio-group">
              <legend>Дія *</legend>
              <label className="radio-card">
                <input type="radio" name="mode" checked={mode === 'new'} onChange={() => selectMode('new')} />
                <span><span className="radio-card__title">Новий набір</span><span className="radio-card__hint">Створити набір з новою назвою</span></span>
              </label>
              <label className="radio-card">
                <input type="radio" name="mode" checked={mode === 'version'} onChange={() => selectMode('version')} />
                <span><span className="radio-card__title">Нова версія існуючого набору</span><span className="radio-card__hint">Додати версію до наявного набору</span></span>
              </label>
            </fieldset>
            {mode === 'version' && (
              <div className={`field${errors.dataset ? ' field--error' : ''}`}>
                <label className="field__label" htmlFor={selectId}>Оберіть існуючий набір *</label>
                <select id={selectId} className="field__input" value={datasetId} onChange={(e) => selectDataset(e.target.value)} aria-invalid={errors.dataset ? true : undefined}>
                  <option value="">{datasets ? 'Оберіть набір' : 'Завантаження списку…'}</option>
                  {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                </select>
                {errors.dataset && <span className="field__error">{errors.dataset}</span>}
                {datasetsError && <span className="field__error">{datasetsError}</span>}
              </div>
            )}
          </section>

          {file ? (
            <div className="file-card">
              <div className="file-card__row">
                <span className="file-card__icon"><IconFile /></span>
                <span className="file-card__text">
                  <span className="file-card__name">{file.name}</span>
                  <span className="file-card__meta">{fileMeta}</span>
                </span>
                <Button variant="danger-soft" onClick={removeFile}>Видалити</Button>
              </div>
              <Alert tone="success">Формат {extOf(file.name).slice(1).toUpperCase()} підтверджено · Розмір в межах ліміту ({MAX_UPLOAD_MB} МБ)</Alert>
            </div>
          ) : (
            <div className={`dropzone${dragOver ? ' is-over' : ''}`} onDragOver={(e) => { e.preventDefault(); setDragOver(true) }} onDragLeave={() => setDragOver(false)} onDrop={handleDrop}>
              <IconUpload size={40} />
              <p className="dropzone__title">Перетягніть файл сюди</p>
              <p>або оберіть його на комп’ютері</p>
              <Button variant="secondary" onClick={() => inputRef.current?.click()}>Обрати файл</Button>
              <p className="caption">Формати: CSV, JSON · до {MAX_UPLOAD_MB} МБ</p>
            </div>
          )}

          {fileProblem && <Alert tone="error" title="Файл не підходить">{fileProblem}</Alert>}
          {errors.file && !file && !fileProblem && <Alert tone="error">{errors.file}</Alert>}

          <div className="actions">
            <Button variant="secondary" onClick={resetAll}>Скасувати</Button>
            <Button type="submit">Імпортувати</Button>
          </div>
        </form>
      )}

      {stage === 'uploading' && file && (
        <div className="upload">
          {summary}
          <div className="file-card">
            <div className="file-card__row">
              <span className="file-card__icon"><IconFile /></span>
              <span className="file-card__text"><span className="file-card__name">{file.name}</span></span>
              <span className="file-card__meta">{fileMeta}</span>
            </div>
            <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} aria-label="Надсилання файлу">
              <div className="progress__bar" style={{ width: `${progress}%` }} />
            </div>
            <p className="file-card__meta">Надсилання файлу на сервер…</p>
          </div>
          <Alert tone="info">Не закривайте вкладку до завершення завантаження</Alert>
        </div>
      )}

      {stage === 'error' && file && (
        <div className="upload">
          {summary}
          <div className="file-card">
            <div className="file-card__row">
              <span className="file-card__icon file-card__icon--bad"><IconFile /></span>
              <span className="file-card__text">
                <span className="file-card__name">{file.name}</span>
                <span className="file-card__meta">{formatSize(file.size)}</span>
              </span>
            </div>
          </div>
          <Alert tone="error" title="Файл не пройшов перевірку">{apiError}</Alert>
          <div className="actions">
            <Button onClick={() => inputRef.current?.click()}>Обрати інший файл</Button>
            <Button variant="secondary" onClick={resetAll}>Скасувати</Button>
          </div>
        </div>
      )}

      {stage === 'success' && file && (
        <div className="upload">
          <div className="success">
            <span className="success__icon"><IconCheckCircle size={28} /></span>
            <h2>Файл успішно завантажено</h2>
            <p>{file.name} · {formatSize(file.size)}</p>
            <StatusBadge value="Uploaded" />
            <ul className="success__rows">
              <li><b>Оригінал файлу</b><span>Збережено без змін</span></li>
              <li><b>Журнал аудиту</b><span>Подію записано</span></li>
              <li><b>Набір даних</b><span>{displayName} · {mode === 'version' ? 'нова версія' : 'новий набір'}</span></li>
            </ul>
          </div>
          <div className="actions" style={{ justifyContent: 'center' }}>
            <Button variant="secondary" onClick={resetAll}>Завантажити ще файл</Button>
            <Button onClick={() => navigate(`/datasets/${result?.dataset_id ?? result?.id ?? ''}`)}>Перейти до профілю</Button>
          </div>
        </div>
      )}
    </>
  )
}
