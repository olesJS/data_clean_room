import { config, endpoints } from '../config'
import { request } from './client'
import {
  mockCheckPublication,
  mockPublishDataset,
} from './mock'
import type {
  PublicationCheck,
  PublishResult,
} from './types'

/**
 * Перевірка готовності до публікації (Publication Gate) — лише читання (UC-07).
 * Працює з реальним API, або mock при VITE_USE_MOCK=true.
 * Без silent fallback при 404/405.
 */
export async function checkPublication(
  datasetId: number | string,
  retentionUntil?: string,
): Promise<PublicationCheck> {
  if (config.useMock) {
    return mockCheckPublication(datasetId, retentionUntil)
  }
  const query = retentionUntil
    ? `?retention_until=${encodeURIComponent(retentionUntil)}`
    : ''
  return request<PublicationCheck>(endpoints.publishCheck(datasetId) + query)
}

/**
 * Опублікувати набір даних (UC-07).
 * Працює з реальним API, або mock при VITE_USE_MOCK=true.
 * Без silent fallback при 404/405.
 */
export async function publishDataset(
  datasetId: number | string,
  retentionUntil: string,
): Promise<PublishResult> {
  if (config.useMock) {
    return mockPublishDataset(datasetId, retentionUntil)
  }
  return request<PublishResult>(endpoints.publish(datasetId), {
    method: 'POST',
    body: { retention_until: retentionUntil },
  })
}
