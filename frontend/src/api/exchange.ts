import { config, endpoints } from '../config'
import { request } from './client'
import { storage } from '../auth/storage'
import type { ExchangeRequest, LegalBasisPurpose } from './types'

export function fetchExchangeRequests(): Promise<ExchangeRequest[]> {
  return request<ExchangeRequest[]>(endpoints.exchangeRequests)
}

export function createExchangeRequest(
  datasetId: number,
  purpose: LegalBasisPurpose,
): Promise<ExchangeRequest> {
  return request<ExchangeRequest>(endpoints.exchangeRequests, {
    method: 'POST',
    body: { dataset_id: datasetId, purpose },
  })
}

export function approveExchangeRequest(
  id: number,
  accessUntil?: string,
  reviewComment?: string,
): Promise<ExchangeRequest> {
  return request<ExchangeRequest>(endpoints.exchangeApprove(id), {
    method: 'POST',
    body: {
      access_until: accessUntil || null,
      review_comment: reviewComment || null,
    },
  })
}

export function rejectExchangeRequest(
  id: number,
  reviewComment: string,
): Promise<ExchangeRequest> {
  return request<ExchangeRequest>(endpoints.exchangeReject(id), {
    method: 'POST',
    body: { review_comment: reviewComment },
  })
}

/**
 * Завантаження очищеної версії. Файл віддається з Authorization-заголовком,
 * тому спершу отримуємо blob, а потім ініціюємо збереження у браузері.
 */
export async function downloadExchangeFile(
  id: number,
  fallbackName: string,
): Promise<void> {
  const headers: Record<string, string> = {}
  const token = storage.getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const response = await fetch(config.apiUrl + endpoints.exchangeDownload(id), {
    headers,
  })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    const detail =
      data && typeof data === 'object' && 'detail' in data
        ? String((data as { detail: unknown }).detail)
        : `Помилка сервера (${response.status})`
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
