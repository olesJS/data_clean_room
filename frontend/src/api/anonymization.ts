import { config, endpoints } from '../config'
import { request } from './client'
import { mockApplyAnonymization, mockPreviewAnonymization } from './mock'
import type {
  AnonymizationMethodName,
  AnonymizationPreview,
  AnonymizedVersion,
} from './types'

/**
 * Отримати попередній перегляд анонімізації (UC-06).
 * Читання без запису на диск і без створення версії.
 */
export async function previewAnonymization(
  datasetId: number | string,
  methods: Record<string, AnonymizationMethodName>,
): Promise<AnonymizationPreview> {
  if (config.useMock) {
    return mockPreviewAnonymization(datasetId, methods)
  }
  return request<AnonymizationPreview>(endpoints.anonymizePreview(datasetId), {
    method: 'POST',
    body: { methods },
  })
}

/**
 * Застосувати анонімізацію та створити очищену версію (kind='clean').
 */
export async function applyAnonymization(
  datasetId: number | string,
  methods: Record<string, AnonymizationMethodName>,
): Promise<AnonymizedVersion> {
  if (config.useMock) {
    return mockApplyAnonymization(datasetId, methods)
  }
  return request<AnonymizedVersion>(endpoints.anonymize(datasetId), {
    method: 'POST',
    body: { methods },
  })
}
