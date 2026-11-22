import { config, endpoints } from '../config'
import { storage } from '../auth/storage'
import { request } from './client'
import {
  mockApproveExchangeRequest,
  mockCatalog,
  mockCreateExchangeRequest,
  mockCreateLegalBasis,
  mockDownloadExchangeFile,
  mockExchangeRequests,
  mockLegalBasis,
  mockRejectExchangeRequest,
  mockRevokeLegalBasis,
} from './mock'
import type {
  CatalogItem,
  CreateExchangeRequestPayload,
  ExchangeRequest,
  LegalBasis,
  LegalBasisCreatePayload,
  ReviewExchangeRequestPayload,
} from './types'

/**
 * Отримати список опублікованих наборів даних для Каталогу (UC-08).
 * Доступно для Data Consumer та Data Steward.
 */
export async function fetchCatalog(): Promise<CatalogItem[]> {
  if (config.useMock) {
    return mockCatalog()
  }
  return request<CatalogItem[]>(endpoints.catalog)
}

/**
 * Отримати список запитів на обмін даними (UC-09).
 * Ролі:
 * - Consumer: власні запити
 * - Steward: усі запити системи
 * - Provider: запити на набори поточного провайдера
 */
export async function fetchExchangeRequests(): Promise<ExchangeRequest[]> {
  if (config.useMock) {
    return mockExchangeRequests()
  }
  return request<ExchangeRequest[]>(endpoints.requests)
}

/**
 * Створити запит на доступ до набору даних (UC-08).
 * Доступно для Data Consumer.
 */
export async function createExchangeRequest(
  datasetIdOrPayload: number | CreateExchangeRequestPayload,
  purposeParam?: string,
): Promise<ExchangeRequest> {
  const dataset_id =
    typeof datasetIdOrPayload === 'number'
      ? datasetIdOrPayload
      : datasetIdOrPayload.dataset_id
  const purpose =
    typeof datasetIdOrPayload === 'number'
      ? (purposeParam ?? '')
      : datasetIdOrPayload.purpose

  if (config.useMock) {
    return mockCreateExchangeRequest(dataset_id, purpose)
  }
  return request<ExchangeRequest>(endpoints.requests, {
    method: 'POST',
    body: { dataset_id, purpose },
  })
}

/**
 * Схвалити запит на доступ (UC-09).
 * Власник набору (DataProvider / DataSteward) схвалює запит після перевірки правової підстави.
 */
export async function approveExchangeRequest(
  id: number,
  commentOrPayload?: string | ReviewExchangeRequestPayload,
): Promise<ExchangeRequest> {
  const comment =
    typeof commentOrPayload === 'string'
      ? commentOrPayload
      : commentOrPayload?.comment ?? undefined

  if (config.useMock) {
    return mockApproveExchangeRequest(id, comment)
  }
  return request<ExchangeRequest>(endpoints.requestApprove(id), {
    method: 'POST',
    body: { comment: comment?.trim() || null },
  })
}

/**
 * Відхилити запит на доступ (UC-09).
 */
export async function rejectExchangeRequest(
  id: number,
  commentOrPayload?: string | ReviewExchangeRequestPayload,
): Promise<ExchangeRequest> {
  const comment =
    typeof commentOrPayload === 'string'
      ? commentOrPayload
      : commentOrPayload?.comment ?? undefined

  if (config.useMock) {
    return mockRejectExchangeRequest(id, comment)
  }
  return request<ExchangeRequest>(endpoints.requestReject(id), {
    method: 'POST',
    body: { comment: comment?.trim() || null },
  })
}

/**
 * Завантажити знеособлену clean-версію набору даних для схваленого запиту (UC-10).
 * Файл завантажується як Blob через авторизований запит.
 */
export async function downloadExchangeFile(
  id: number,
  fallbackName = 'clean_dataset.csv',
): Promise<void> {
  if (config.useMock) {
    return mockDownloadExchangeFile(id, fallbackName)
  }

  const headers: Record<string, string> = {}
  const token = storage.getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const response = await fetch(config.apiUrl + endpoints.requestDownload(id), {
    headers,
  })

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    let detail =
      data && typeof data === 'object' && 'detail' in data
        ? String((data as { detail: unknown }).detail)
        : ''

    if (response.status === 403) {
      if (
        detail.toLowerCase().includes('revoked') ||
        detail.toLowerCase().includes('no longer valid')
      ) {
        detail = 'Згоду або правову підставу відкликано — завантаження неможливе.'
      } else {
        detail = detail || 'Немає прав для завантаження набору даних.'
      }
    } else if (response.status === 404) {
      detail = 'Очищену версію набору не знайдено або запит не належить користувачу.'
    } else if (response.status === 409) {
      detail = detail || 'Конфлікт статусу запиту або правової підстави.'
    } else if (!detail) {
      detail = `Помилка завантаження файлу (${response.status})`
    }

    throw new Error(detail)
  }

  const disposition = response.headers.get('content-disposition') ?? ''
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition)
  const fileName = match ? decodeURIComponent(match[1]) : fallbackName
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

/**
 * Отримати список правових підстав для набору даних (UC-12).
 */
export async function fetchLegalBasis(datasetId: number | string): Promise<LegalBasis[]> {
  if (config.useMock) {
    return mockLegalBasis(datasetId)
  }
  return request<LegalBasis[]>(endpoints.legalBasis(datasetId))
}

/**
 * Зареєструвати нову правову підставу для набору (UC-12).
 */
export async function createLegalBasis(
  datasetId: number | string,
  payload: LegalBasisCreatePayload,
): Promise<LegalBasis> {
  if (config.useMock) {
    return mockCreateLegalBasis(datasetId, payload)
  }
  return request<LegalBasis>(endpoints.legalBasis(datasetId), {
    method: 'POST',
    body: payload,
  })
}

/**
 * Відкликати правову підставу (згоду) за її ID (UC-12).
 */
export async function revokeLegalBasis(
  id: string | number,
  reason?: string,
): Promise<LegalBasis> {
  const idStr = String(id)
  const reasonStr = reason?.trim() || ''
  if (config.useMock) {
    return mockRevokeLegalBasis(idStr, reasonStr)
  }
  return request<LegalBasis>(endpoints.legalBasisRevoke(idStr), {
    method: 'POST',
    body: { reason: reasonStr },
  })
}
