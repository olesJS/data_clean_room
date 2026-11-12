import { endpoints } from '../config'
import { request } from './client'
import type {
  AnonymizationMethodName,
  AnonymizationPreview,
  AnonymizedVersion,
  DatasetVersionInfo,
  LegalBasis,
  LegalBasisCreatePayload,
  PublicationCheck,
  PublishResult,
} from './types'

export function fetchLegalBasis(datasetId: number | string): Promise<LegalBasis[]> {
  return request<LegalBasis[]>(endpoints.legalBasis(datasetId))
}

export function createLegalBasis(
  datasetId: number | string,
  payload: LegalBasisCreatePayload,
): Promise<LegalBasis> {
  return request<LegalBasis>(endpoints.legalBasis(datasetId), {
    method: 'POST',
    body: payload,
  })
}

export function revokeLegalBasis(id: string, reason: string): Promise<LegalBasis> {
  return request<LegalBasis>(endpoints.legalBasisRevoke(id), {
    method: 'POST',
    body: { reason },
  })
}

export function previewAnonymization(
  datasetId: number | string,
  methods: Record<string, AnonymizationMethodName>,
): Promise<AnonymizationPreview> {
  return request<AnonymizationPreview>(endpoints.anonymizePreview(datasetId), {
    method: 'POST',
    body: { methods },
  })
}

export function applyAnonymization(
  datasetId: number | string,
  methods: Record<string, AnonymizationMethodName>,
): Promise<AnonymizedVersion> {
  return request<AnonymizedVersion>(endpoints.anonymize(datasetId), {
    method: 'POST',
    body: { methods },
  })
}

export function checkPublication(
  datasetId: number | string,
  retentionUntil?: string,
): Promise<PublicationCheck> {
  const query = retentionUntil
    ? `?retention_until=${encodeURIComponent(retentionUntil)}`
    : ''
  return request<PublicationCheck>(endpoints.publishCheck(datasetId) + query)
}

export function publishDataset(
  datasetId: number | string,
  retentionUntil: string,
): Promise<PublishResult> {
  return request<PublishResult>(endpoints.publish(datasetId), {
    method: 'POST',
    body: { retention_until: retentionUntil },
  })
}

export function fetchDatasetVersions(
  datasetId: number | string,
): Promise<DatasetVersionInfo[]> {
  return request<DatasetVersionInfo[]>(endpoints.datasetVersions(datasetId))
}
