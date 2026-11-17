import { config, endpoints } from '../config'
import { request } from './client'
import {
  mockCheckPublication,
  mockCreateLegalBasis,
  mockDatasetVersions,
  mockLegalBasis,
  mockPublishDataset,
  mockRevokeLegalBasis,
} from './mock'
import type {
  DatasetVersionInfo,
  LegalBasis,
  LegalBasisCreatePayload,
  PublicationCheck,
  PublishResult,
} from './types'

/**
 * Отримати список правових підстав для набору даних.
 */
export async function fetchLegalBasis(datasetId: number | string): Promise<LegalBasis[]> {
  if (config.useMock) {
    return mockLegalBasis(datasetId)
  }
  return request<LegalBasis[]>(endpoints.legalBasis(datasetId))
}

/**
 * Зареєструвати нову правову підставу для набору.
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
 * Відкликати правову підставу за її ID.
 */
export async function revokeLegalBasis(id: string, reason: string): Promise<LegalBasis> {
  if (config.useMock) {
    return mockRevokeLegalBasis(id, reason)
  }
  return request<LegalBasis>(endpoints.legalBasisRevoke(id), {
    method: 'POST',
    body: { reason },
  })
}

/**
 * Перевірка готовності до публікації (Publication Gate) — лише читання.
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

/**
 * Отримати список версій набору даних (raw / clean).
 */
export async function fetchDatasetVersions(
  datasetId: number | string,
): Promise<DatasetVersionInfo[]> {
  if (config.useMock) {
    return mockDatasetVersions(datasetId)
  }
  return request<DatasetVersionInfo[]>(endpoints.datasetVersions(datasetId))
}
