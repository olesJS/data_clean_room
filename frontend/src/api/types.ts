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
