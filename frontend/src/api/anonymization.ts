import { config, endpoints } from '../config'
import { request } from './client'
import { mockApplyAnonymization, mockPreviewAnonymization } from './mock'
import type {
  AnonymizationColumn,
  AnonymizationMethodName,
  AnonymizationPreview,
  AnonymizationPreviewRow,
  AnonymizedVersion,
  DataClass,
} from './types'

/**
 * Отримати попередній перегляд анонімізації (UC-06).
 * Читання без запису на диск і без створення версії.
 * Підтримує контракти як #43 ({ columns }), так і #33/{#28} ({ methods }).
 */
export async function previewAnonymization(
  datasetId: number | string,
  methods: Record<string, AnonymizationMethodName>,
): Promise<AnonymizationPreview> {
  if (config.useMock) {
    return mockPreviewAnonymization(datasetId, methods)
  }

  // Надсилаємо обидва поля columns і methods для сумісності з обома контрактами бекенду
  const raw = await request<Record<string, unknown>>(endpoints.anonymizePreview(datasetId), {
    method: 'POST',
    body: {
      columns: methods,
      methods,
    },
  })

  const hasHmac = Object.values(methods).some((m) => m.toLowerCase().includes('hmac'))
  const fallbackClass: DataClass = hasHmac ? 'Personal' : 'Confidential'

  // Випадок 1: Формат бекенду #43: columns = { [colName]: { before: [...], after: [...] } }
  if (
    raw.columns &&
    typeof raw.columns === 'object' &&
    !Array.isArray(raw.columns)
  ) {
    const colEntries = Object.entries(
      raw.columns as Record<string, { before?: unknown[]; after?: unknown[] }>,
    )
    const rowCount = Number(
      raw.preview_rows_count ?? (colEntries[0]?.[1]?.before?.length || 0),
    )

    const previewPairs: AnonymizationPreviewRow[] = []
    for (let i = 0; i < rowCount; i++) {
      const original: Record<string, string> = { row_index: String(i + 1) }
      const anonymized: Record<string, string> = { row_index: String(i + 1) }

      for (const [colName, pair] of colEntries) {
        original[colName] =
          pair.before?.[i] !== undefined && pair.before?.[i] !== null
            ? String(pair.before[i])
            : ''
        anonymized[colName] =
          pair.after?.[i] !== undefined && pair.after?.[i] !== null
            ? String(pair.after[i])
            : ''
      }
      previewPairs.push({ row_index: i + 1, original, anonymized })
    }

    const columnsList: AnonymizationColumn[] = colEntries.map(([colName]) => ({
      column_name: colName,
      pii_type: 'pii',
      method: methods[colName] ?? 'mask',
    }))

    return {
      dataset_id: Number(raw.dataset_id ?? datasetId),
      dataset_name: (raw.dataset_name as string) || undefined,
      pii_columns_count: colEntries.length,
      estimated_class: (raw.estimated_class as DataClass) || fallbackClass,
      hmac_requires_legal_basis: Boolean(raw.hmac_requires_legal_basis ?? hasHmac),
      columns: columnsList,
      preview_pairs: previewPairs,
    }
  }

  // Випадок 2: Формат зі списком columns: AnonymizationColumn[]
  const columnsList: AnonymizationColumn[] = Array.isArray(raw.columns)
    ? (raw.columns as AnonymizationColumn[])
    : Object.keys(methods).map((colName) => ({
        column_name: colName,
        pii_type: 'pii',
        method: methods[colName] ?? 'mask',
      }))

  return {
    dataset_id: Number(raw.dataset_id ?? datasetId),
    dataset_name: (raw.dataset_name as string) || undefined,
    pii_columns_count: Number(raw.pii_columns_count ?? columnsList.length),
    estimated_class: (raw.estimated_class as DataClass) || fallbackClass,
    hmac_requires_legal_basis: Boolean(raw.hmac_requires_legal_basis ?? hasHmac),
    columns: columnsList,
    sample_rows: raw.sample_rows as Record<string, string>[] | undefined,
    preview_pairs: raw.preview_pairs as AnonymizationPreviewRow[] | undefined,
  }
}

/**
 * Застосувати анонімізацію та створити очищену версію (kind='clean').
 * Нормалізує відповіді як від #43 ({ clean_sha256, status, applied_columns }),
 * так і повний об'єкт версії від #33.
 */
export async function applyAnonymization(
  datasetId: number | string,
  methods: Record<string, AnonymizationMethodName>,
): Promise<AnonymizedVersion> {
  if (config.useMock) {
    return mockApplyAnonymization(datasetId, methods)
  }

  const raw = await request<Record<string, unknown>>(endpoints.anonymize(datasetId), {
    method: 'POST',
    body: {
      columns: methods,
      methods,
    },
  })

  const hasHmac = Object.values(methods).some((m) => m.toLowerCase().includes('hmac'))
  const sha = (raw.clean_sha256 as string) || (raw.sha256 as string) || ''
  const fileStem = `clean_dataset_${datasetId}`

  return {
    dataset_id: Number(raw.dataset_id ?? datasetId),
    version_id: Number(raw.version_id ?? 1),
    version_number: Number(raw.version_number ?? 1),
    kind: 'clean',
    file_name: (raw.file_name as string) || `${fileStem}.csv`,
    row_count: Number(raw.row_count ?? 0),
    sha256: sha,
    data_class: (raw.data_class as DataClass) || (hasHmac ? 'Personal' : 'Confidential'),
    created_at: (raw.created_at as string) || new Date().toISOString(),
  }
}
