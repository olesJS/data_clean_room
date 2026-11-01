import { ApiError } from './client'
import type { DatasetVersion, DatasetProfileResponse, DatasetPIIResponse, LoginResponse, Role, UploadResult, User } from './types'
import { storage } from '../auth/storage'

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))

/**
 * Заглушка входу. Роль за поштою: steward / consumer / решта = provider.
 * Пароль "wrong" дає 401, пошта з "locked" дає 423 (тимчасове блокування).
 */
export async function mockLogin(email: string, password: string): Promise<LoginResponse> {
  await delay(500)
  if (email.includes('locked')) throw new ApiError('Account temporarily locked', 423)
  if (password === 'wrong') throw new ApiError('Invalid credentials', 401)
  const role: Role = email.includes('steward') ? 'DataSteward' : email.includes('consumer') ? 'DataConsumer' : 'DataProvider'
  return { access_token: 'mock-token', token_type: 'bearer', role }
}

export async function mockMe(): Promise<User> {
  await delay(150)
  return { id: 1, email: storage.getEmail() ?? 'provider@example.com', role: storage.getRole() ?? 'DataProvider' }
}

const v = (id: number, dataset_id: number, dataset_name: string, file_name: string, format: 'CSV' | 'JSON', data_class: DatasetVersion['data_class'], status: DatasetVersion['status'], quality_score: number, version_number: number, parent_version_id: number | null, updated_at: string): DatasetVersion =>
  ({ id, dataset_id, dataset_name, file_name, format, data_class, status, quality_score, version_number, parent_version_id, updated_at })

export async function mockDatasets(): Promise<DatasetVersion[]> {
  await delay(300)
  return [
    v(1, 101, 'Payroll 2026', 'payroll_2026.csv', 'CSV', 'Personal', 'Needs attention', 72, 1, null, '2026-10-19'),
    v(2, 101, 'Payroll 2026', 'payroll_2026_clean.csv', 'CSV', 'Confidential', 'Published', 96, 2, 1, '2026-10-19'),
    v(3, 103, 'Customers', 'customers.json', 'JSON', 'Personal', 'Needs attention', 49, 1, null, '2026-10-20'),
    v(4, 103, 'Customers', 'customers_clean.json', 'JSON', 'Confidential', 'Published', 94, 2, 3, '2026-10-21'),
    v(5, 105, 'Store catalog', 'store_catalog.csv', 'CSV', 'Public', 'Published', 99, 1, null, '2026-10-22'),
  ]
}

export async function mockUpload(onProgress: (percent: number) => void): Promise<UploadResult> {
  for (let p = 0; p <= 100; p += 10) {
    onProgress(p)
    await delay(250)
  }
  return { id: 6, dataset_id: 101 }
}

// ---------------------------------------------------------------------------
// Sprint 2 — mock profile & PII
// ---------------------------------------------------------------------------

export async function mockDatasetProfile(datasetId: number): Promise<DatasetProfileResponse> {
  await delay(400)
  return {
    dataset_id: datasetId,
    dataset_name: 'Mock Dataset',
    data_class: 'Confidential',
    quality_score: 87.5,
    summary: {
      total_rows: 1000,
      total_columns: 4,
      duplicate_rows_count: 12,
      rules_violated_count: 2,
    },
    columns: [
      {
        name: 'email',
        type: 'string',
        null_count: 5,
        null_percentage: 0.5,
        unique_count: 990,
        is_pii: true,
        pii_type: 'EMAIL',
        pii_confidence: 0.95,
        min: null,
        max: null,
        mean: null,
        outliers_count: 0,
        histogram: null,
      },
      {
        name: 'age',
        type: 'numeric',
        null_count: 0,
        null_percentage: 0,
        unique_count: 60,
        is_pii: false,
        pii_type: null,
        pii_confidence: null,
        min: 18,
        max: 85,
        mean: 38.4,
        outliers_count: 3,
        histogram: {
          bins: ['(18, 30]', '(30, 42]', '(42, 54]', '(54, 66]', '(66, 85]'],
          counts: [280, 340, 210, 120, 50],
        },
      },
      {
        name: 'full_name',
        type: 'string',
        null_count: 10,
        null_percentage: 1.0,
        unique_count: 985,
        is_pii: true,
        pii_type: 'NAME',
        pii_confidence: 0.75,
        min: null,
        max: null,
        mean: null,
        outliers_count: 0,
        histogram: null,
      },
      {
        name: 'salary',
        type: 'numeric',
        null_count: 0,
        null_percentage: 0,
        unique_count: 450,
        is_pii: false,
        pii_type: null,
        pii_confidence: null,
        min: 5000,
        max: 250000,
        mean: 42300.0,
        outliers_count: 7,
        histogram: {
          bins: ['(5000, 54000]', '(54000, 103000]', '(103000, 152000]', '(152000, 201000]', '(201000, 250000]'],
          counts: [620, 210, 90, 55, 25],
        },
      },
    ],
  }
}

export async function mockDatasetPII(datasetId: number): Promise<DatasetPIIResponse> {
  await delay(300)
  const profile = await mockDatasetProfile(datasetId)
  return {
    dataset_id: datasetId,
    data_class: profile.data_class,
    pii_columns: profile.columns.filter((c) => c.is_pii),
  }
}
