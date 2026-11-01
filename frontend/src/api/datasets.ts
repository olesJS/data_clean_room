import { config, endpoints } from '../config'
import { ApiError, NETWORK_ERROR, extractError, notifyUnauthorized, request } from './client'
import { mockDatasetProfile, mockDatasets, mockDeleteDataset, mockPiiScan, mockPiiUpdate, mockUpload } from './mock'
import { storage } from '../auth/storage'
import type {
  DatasetProfileResponse,
  DatasetVersion,
  PiiFinding,
  PiiScanResponse,
  PiiUpdatePayload,
  UploadResult,
} from './types'

/** GET /datasets. Мапимо бекенд-відповідь на інтерфейс фронтенду DatasetVersion */
export async function fetchDatasets(): Promise<DatasetVersion[]> {
  if (config.useMock) return mockDatasets()
  const rawList = await request<any[]>(endpoints.datasets)

  return rawList.map((item) => ({
    id: item.id,
    dataset_id: item.id,
    dataset_name: item.name,
    file_name: item.original_filename || item.name,
    format: (item.file_type || 'CSV').toUpperCase() as 'CSV' | 'JSON',
    data_class: item.data_class || 'Internal',
    status: item.status || 'Uploaded',
    quality_score: item.quality_score ?? null,
    version_number: 1,
    parent_version_id: null,
    updated_at: item.created_at || new Date().toISOString(),
  }))
}

/** GET /api/datasets/:id/profile — профіль набору та Quality Score. */
export function fetchDatasetProfile(id: number | string): Promise<DatasetProfileResponse> {
  if (config.useMock) return mockDatasetProfile(id)
  return request<DatasetProfileResponse>(endpoints.datasetProfile(id))
}

/** GET /api/datasets/:id/pii — результати PII-сканування. */
export function fetchPiiScan(id: number | string): Promise<PiiScanResponse> {
  if (config.useMock) return mockPiiScan(id)
  return request<PiiScanResponse>(endpoints.datasetPii(id))
}

/** PATCH /api/datasets/:id/pii/:col — підтвердити або виправити PII-класифікацію колонки. */
export function updatePiiColumn(
  id: number | string,
  columnName: string,
  payload: PiiUpdatePayload
): Promise<PiiFinding> {
  if (config.useMock) return mockPiiUpdate(id, columnName, payload)
  return request<PiiFinding>(endpoints.datasetPiiColumn(id, columnName), {
    method: 'PATCH',
    body: payload,
  })
}

/** DELETE /api/datasets/:id — видалити набір даних. */
export async function deleteDataset(id: number | string): Promise<void> {
  if (config.useMock) return mockDeleteDataset(id)
  return request<void>(endpoints.datasetDelete(id), { method: 'DELETE' })
}

interface UploadParams {
  name: string
  file: File
  /** Якщо задано, файл стає новою версією цього набору. */
  datasetId?: number
  onProgress: (percent: number) => void
}

/**
 * POST /datasets (multipart/form-data: поля `name`, `file` і необов'язкове `dataset_id`).
 * XMLHttpRequest потрібен, бо fetch не показує прогрес відправки.
 */
export function uploadDataset({ name, file, datasetId, onProgress }: UploadParams): Promise<UploadResult> {
  if (config.useMock) return mockUpload(onProgress)

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', config.apiUrl + endpoints.datasets)
    const token = storage.getToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onerror = () => reject(new ApiError(NETWORK_ERROR, 0))
    xhr.onload = () => {
      let data: unknown = null
      try { data = JSON.parse(xhr.responseText) } catch { /* відповідь без JSON */ }
      if (xhr.status === 401) notifyUnauthorized()
      if (xhr.status >= 200 && xhr.status < 300) resolve((data ?? {}) as UploadResult)
      else reject(new ApiError(extractError(data, `Помилка сервера (${xhr.status})`), xhr.status))
    }

    const form = new FormData()
    form.append('name', name)
    form.append('file', file)
    if (datasetId !== undefined) form.append('dataset_id', String(datasetId))
    xhr.send(form)
  })
}
