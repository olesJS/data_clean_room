export type Role = 'DataProvider' | 'DataConsumer' | 'DataSteward'

export const ROLE_LABELS: Record<Role, string> = {
  DataProvider: 'Data Provider',
  DataConsumer: 'Data Consumer',
  DataSteward: 'Data Steward',
}

export interface LoginResponse {
  access_token: string
  token_type: string
  role: Role
}

export interface User {
  id: number
  email: string
  role: Role
}

export type DataClass = 'Public' | 'Internal' | 'Confidential' | 'Personal'
export type VersionStatus = 'Uploaded' | 'Profiled' | 'Needs attention' | 'Published' | 'Expired'

export const STATUS_LABELS: Record<VersionStatus, string> = {
  Uploaded: 'Завантажено',
  Profiled: 'Профільовано',
  'Needs attention': 'Потребує уваги',
  Published: 'Опубліковано',
  Expired: 'Термін минув',
}

/**
 * Одна версія набору. Форма відповіді GET /datasets ПРИПУЩЕНА, її треба узгодити з D.
 * Очищена версія посилається на оригінал через parent_version_id.
 */
export interface DatasetVersion {
  id: number
  dataset_id: number
  dataset_name: string
  file_name: string
  format: 'CSV' | 'JSON'
  data_class: DataClass
  status: VersionStatus
  quality_score: number | null
  version_number: number
  parent_version_id: number | null
  updated_at: string
}

export interface UploadResult {
  id?: number
  dataset_id?: number
  [key: string]: unknown
}

// ─── Profiling types (DCR-45) ─────────────────────────────────────────────────

export interface ColumnHistogram {
  bins: string[]
  counts: number[]
}

export type ColumnDataType = 'string' | 'numeric' | 'datetime' | 'boolean'

export interface ColumnProfile {
  name: string
  type: ColumnDataType
  null_count: number
  null_percentage: number
  unique_count: number
  is_pii: boolean
  pii_type: string | null
  pii_confidence: number | null
  min: number | string | null
  max: number | string | null
  mean: number | null
  outliers_count: number
  histogram: ColumnHistogram | null
}

export interface DatasetProfileSummary {
  total_rows: number
  total_columns: number
  duplicate_rows_count: number
  rules_violated_count: number
}

export interface DatasetProfileResponse {
  dataset_id: number
  dataset_name: string
  data_class: DataClass
  quality_score: number
  summary: DatasetProfileSummary
  columns: ColumnProfile[]
}

// ─── PII scan types (SCRUM-33) ────────────────────────────────────────────────

export type PiiType =
  | 'UA_IPN'
  | 'UA_FULL_NAME'
  | 'UA_IBAN'
  | 'UA_PHONE'
  | 'UA_PASSPORT'
  | 'EMAIL'
  | 'CREDIT_CARD'
  | 'DATE_OF_BIRTH'
  | 'UA_ADDRESS'
  | null

/** Знахідка PII для однієї колонки набору даних. */
export interface PiiFinding {
  column_name: string
  pii_type: PiiType
  confidence: number
  sample_masked: string | null
  detection_method: string
  /** null = очікує підтвердження, true = підтверджено, false = відхилено */
  user_confirmed: boolean | null
  corrected_pii_type?: PiiType
}

/** Тіло запиту PATCH /api/datasets/:id/pii/:column для підтвердження/виправлення. */
export interface PiiUpdatePayload {
  user_confirmed: boolean
  corrected_pii_type?: PiiType
}

/** Відповідь GET /api/datasets/:id/pii */
export interface PiiScanResponse {
  dataset_id: number
  dataset_name: string
  data_class: DataClass
  pii_columns_count: number
  total_columns: number
  findings: PiiFinding[]
}
