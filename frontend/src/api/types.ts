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

// ─── PII scan types ───────────────────────────────────────────────────────────

export type PiiType =
  | 'person_name'
  | 'ipn'
  | 'passport'
  | 'iban'
  | 'card'
  | 'email'
  | 'phone'
  | 'address'
  | 'birth_date'
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

// ─── Quality Rules & Violations types (SCRUM-49) ──────────────────────────────

export type QualityAction = 'reject' | 'flag' | 'block'

export interface QualityRule {
  column: string // '*' для перевірок усього рядка
  condition: string // "between(0, 120)", "> 0", "email", "not_null", "<= today"
  action: QualityAction
  description: string
}

export interface QualityViolation {
  column: string
  condition: string
  action: QualityAction
  violation_count: number
  is_blocking: boolean
  message?: string
  violating_indices?: number[] | null // віддається лише за ?include_indices=true, екран не використовує
}

export interface QualityReport {
  dataset_id: number
  score: number
  total_rows: number
  unique_violating_rows: number
  can_publish: boolean
  has_blocking_violations: boolean
  action_counts: Record<QualityAction, number>
  summary?: { duplicate_rows_count?: number }
  violations: QualityViolation[]
}

// ─── Sprint 3: публікація, правова підстава, обмін ───────────────────────────

export type LegalBasisType = 'consent' | 'contract' | 'law'
export type LegalBasisPurpose = 'analytics' | 'research' | 'reporting' | 'publication'

export const LEGAL_BASIS_TYPE_LABELS: Record<LegalBasisType, string> = {
  consent: 'Згода',
  contract: 'Договір',
  law: 'Закон',
}

export const LEGAL_BASIS_PURPOSE_LABELS: Record<LegalBasisPurpose, string> = {
  analytics: 'Аналітика',
  research: 'Дослідження',
  reporting: 'Звітність',
  publication: 'Публікація',
}

export interface LegalBasis {
  id: string
  dataset_id: number
  type: LegalBasisType
  document_ref: string
  date: string
  purpose: LegalBasisPurpose
  valid_until: string | null
  entered_by: number
  created_at: string
  revoked_at: string | null
  revoked_by: number | null
  revoked_reason: string | null
  is_active: boolean
}

export interface LegalBasisCreatePayload {
  type: LegalBasisType
  document_ref: string
  date: string
  purpose: LegalBasisPurpose
  valid_until?: string | null
}

export type AnonymizationMethodName = 'mask' | 'generalize' | 'hmac' | 'redact'

export interface AnonymizationColumn {
  column_name: string
  pii_type: string
  method: AnonymizationMethodName
}

export interface AnonymizationPreview {
  dataset_id: number
  pii_columns_count: number
  estimated_class: DataClass
  columns: AnonymizationColumn[]
  sample_rows?: Record<string, string>[]
}

export interface AnonymizedVersion {
  dataset_id: number
  version_id: number
  version_number: number
  kind: 'clean'
  file_name: string
  row_count: number
  sha256: string
  data_class: DataClass
  created_at: string
}

export interface DatasetVersionInfo {
  id: number
  kind: 'raw' | 'clean'
  version_number: number
  file_name: string
  file_type: string
  file_size: number
  row_count: number
  sha256: string
  data_class: DataClass | null
  created_by: string
  created_at: string
}

export interface PublicationReason {
  code: string
  short_code: string
  message: string
  columns?: string[]
  legal_basis_reason?: string
}

export interface PublicationCheck {
  allowed: boolean
  reasons: PublicationReason[]
  new_class: DataClass
  hmac_columns: string[]
  missing_columns: string[]
  clean_version_id: number | null
}

export interface PublishResult {
  dataset_id: number
  status: string
  data_class: DataClass
  published_at: string
  published_by: string
  retention_until: string
  gate: PublicationCheck
}

export interface CatalogItem {
  dataset_id: number
  name: string
  data_class: DataClass
  quality_score: number | null
  row_count: number
  column_count: number
  published_at: string | null
  retention_until: string | null
  clean_version_id: number | null
  provider: string
}

export type ExchangeStatus =
  | 'Requested'
  | 'Approved'
  | 'Rejected'
  | 'Downloaded'
  | 'Expired'

export const EXCHANGE_STATUS_LABELS: Record<ExchangeStatus, string> = {
  Requested: 'Очікує рішення',
  Approved: 'Схвалено',
  Rejected: 'Відхилено',
  Downloaded: 'Завантажено',
  Expired: 'Термін минув',
}

export interface ExchangeRequest {
  id: number
  dataset_id: number
  dataset_name: string
  dataset_version_id: number | null
  requester_id: number
  requester_email: string
  reviewer_id: number | null
  reviewer_email: string | null
  status: ExchangeStatus
  purpose: LegalBasisPurpose
  requested_at: string
  decided_at: string | null
  review_comment: string | null
  access_until: string | null
  downloaded_at: string | null
  created_at: string
  updated_at: string
}

export interface AuditLogEntry {
  id: number
  timestamp: string
  actor: string
  action: string
  object: string
  result: string
}
