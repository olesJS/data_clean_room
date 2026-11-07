// frontend/src/api/quality.ts
// Запити для екрана «Правила якості та порушення» (SCRUM-49). Мок вмикається через config.useMock.

import { request } from './client'
import { config, endpoints } from '../config'
import { mockQualityReport, mockQualityRules } from './mock'
import type { QualityReport, QualityRule } from './types'

export function getQualityRules(datasetId: number | string): Promise<QualityRule[]> {
  if (config.useMock) return mockQualityRules(datasetId)
  return request<QualityRule[]>(endpoints.datasetQualityRules(datasetId))
}

export function getQualityReport(datasetId: number | string, action?: string): Promise<QualityReport> {
  if (config.useMock) return mockQualityReport(datasetId)
  return request<QualityReport>(endpoints.datasetQualityViolations(datasetId, action))
}
