// frontend/src/api/quality.ts
// Запити для екрана «Правила якості та порушення» (SCRUM-49). Мок вмикається через config.useMock.

import { request } from './client'
import { config, endpoints } from '../config'
import { mockQualityReport, mockQualityRules } from './mock'
import type { QualityAction, QualityReport, QualityRule, QualityViolation } from './types'

export function getQualityRules(datasetId: number | string): Promise<QualityRule[]> {
  if (config.useMock) return mockQualityRules(datasetId)
  return request<QualityRule[]>(endpoints.datasetQualityRules(datasetId))
}

export async function getQualityReport(datasetId: number | string): Promise<QualityReport> {
  if (config.useMock) return mockQualityReport(datasetId)
  const raw = await request<Record<string, unknown>>(endpoints.datasetQualityViolations(datasetId))
  const violations = (raw.violations as QualityViolation[] | undefined) ?? []
  const counts: Record<QualityAction, number> = { reject: 0, flag: 0, block: 0 }
  for (const v of violations) {
    if (counts[v.action] !== undefined) {
      counts[v.action] += v.violation_count
    }
  }

  return {
    dataset_id: Number(datasetId),
    score: Number(raw.score ?? raw.Score ?? 0),
    total_rows: Number(raw.total_rows ?? 0),
    unique_violating_rows: Number(raw.unique_violating_rows ?? 0),
    can_publish: Boolean(raw.can_publish ?? true),
    has_blocking_violations: Boolean(raw.has_blocking_violations ?? false),
    action_counts: (raw.action_counts as Record<QualityAction, number>) ?? counts,
    summary: {
      duplicate_rows_count: Number(
        raw.duplicated_rows_count ?? ((raw.summary as Record<string, unknown> | undefined)?.duplicate_rows_count ?? 0)
      ),
    },
    violations,
  }
}

