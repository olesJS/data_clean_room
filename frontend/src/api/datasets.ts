import { config, endpoints } from '../config'
import { ApiError, NETWORK_ERROR, extractError, notifyUnauthorized, request } from './client'
import { mockDatasets, mockUpload } from './mock'
import { storage } from '../auth/storage'
import type { DatasetVersion, UploadResult } from './types'

/** GET /datasets. Форму відповіді треба підтвердити з D. */
export function fetchDatasets(): Promise<DatasetVersion[]> {
  if (config.useMock) return mockDatasets()
  return request<DatasetVersion[]>(endpoints.datasets)
}

interface UploadParams {
  name: string
  file: File
  /** Якщо задано, файл стає новою версією цього набору. */
  datasetId?: number
  onProgress: (percent: number) => void
}

/**
 * POST /datasets (multipart/form-data: поля `name`, `file` і необов’язкове `dataset_id`).
 * XMLHttpRequest потрібен, бо fetch не показує прогрес відправки.
 * Назви полів треба підтвердити з D.
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
