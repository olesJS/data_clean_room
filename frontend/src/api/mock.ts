import { ApiError } from './client'
import type { DatasetProfileResponse, DatasetVersion, LoginResponse, Role, UploadResult, User } from './types'
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

const mockPayrollProfile: DatasetProfileResponse = {
  dataset_id: 1,
  dataset_name: 'payroll.csv',
  data_class: 'Personal',
  quality_score: 91.8,
  summary: {
    total_rows: 500,
    total_columns: 6,
    duplicate_rows_count: 10,
    rules_violated_count: 41,
  },
  columns: [
    {
      name: 'ipn',
      type: 'string',
      null_count: 15,
      null_percentage: 3.0,
      unique_count: 475,
      is_pii: true,
      pii_type: 'UA_IPN',
      pii_confidence: 0.98,
      min: null,
      max: null,
      mean: null,
      outliers_count: 0,
      histogram: null,
    },
    {
      name: 'full_name',
      type: 'string',
      null_count: 0,
      null_percentage: 0.0,
      unique_count: 480,
      is_pii: true,
      pii_type: 'UA_FULL_NAME',
      pii_confidence: 0.95,
      min: null,
      max: null,
      mean: null,
      outliers_count: 0,
      histogram: null,
    },
    {
      name: 'iban',
      type: 'string',
      null_count: 0,
      null_percentage: 0.0,
      unique_count: 490,
      is_pii: true,
      pii_type: 'UA_IBAN',
      pii_confidence: 0.99,
      min: null,
      max: null,
      mean: null,
      outliers_count: 0,
      histogram: null,
    },
    {
      name: 'position',
      type: 'string',
      null_count: 0,
      null_percentage: 0.0,
      unique_count: 18,
      is_pii: false,
      pii_type: null,
      pii_confidence: null,
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
      null_percentage: 0.0,
      unique_count: 310,
      is_pii: false,
      pii_type: null,
      pii_confidence: null,
      min: -500.0,
      max: 150000.0,
      mean: 24500.0,
      outliers_count: 13,
      histogram: {
        bins: ['0-10k', '10k-20k', '20k-30k', '30k-50k', '>50k'],
        counts: [50, 350, 75, 12, 13],
      },
    },
    {
      name: 'payment_date',
      type: 'datetime',
      null_count: 0,
      null_percentage: 0.0,
      unique_count: 12,
      is_pii: false,
      pii_type: null,
      pii_confidence: null,
      min: '2026-01-01',
      max: '2027-05-15',
      mean: null,
      outliers_count: 8,
      histogram: null,
    },
  ],
}

const mockCustomersProfile: DatasetProfileResponse = {
  dataset_id: 103,
  dataset_name: 'customers.json',
  data_class: 'Personal',
  quality_score: 87.0,
  summary: {
    total_rows: 1000,
    total_columns: 8,
    duplicate_rows_count: 15,
    rules_violated_count: 130,
  },
  columns: [
    {
      name: 'customer_id',
      type: 'numeric',
      null_count: 0,
      null_percentage: 0.0,
      unique_count: 985,
      is_pii: false,
      pii_type: null,
      pii_confidence: null,
      min: 1,
      max: 1000,
      mean: 500.5,
      outliers_count: 0,
      histogram: {
        bins: ['1-200', '201-400', '401-600', '601-800', '801-1000'],
        counts: [200, 200, 200, 200, 200],
      },
    },
    {
      name: 'name',
      type: 'string',
      null_count: 0,
      null_percentage: 0.0,
      unique_count: 940,
      is_pii: true,
      pii_type: 'UA_FULL_NAME',
      pii_confidence: 0.94,
      min: null,
      max: null,
      mean: null,
      outliers_count: 0,
      histogram: null,
    },
    {
      name: 'email',
      type: 'string',
      null_count: 0,
      null_percentage: 0.0,
      unique_count: 975,
      is_pii: true,
      pii_type: 'EMAIL',
      pii_confidence: 0.99,
      min: null,
      max: null,
      mean: null,
      outliers_count: 25,
      histogram: null,
    },
    {
      name: 'phone',
      type: 'string',
      null_count: 0,
      null_percentage: 0.0,
      unique_count: 980,
      is_pii: true,
      pii_type: 'UA_PHONE',
      pii_confidence: 0.98,
      min: null,
      max: null,
      mean: null,
      outliers_count: 0,
      histogram: null,
    },
    {
      name: 'birth_date',
      type: 'datetime',
      null_count: 0,
      null_percentage: 0.0,
      unique_count: 890,
      is_pii: true,
      pii_type: 'DATE_OF_BIRTH',
      pii_confidence: 0.92,
      min: '1940-02-14',
      max: '2024-11-01',
      mean: null,
      outliers_count: 0,
      histogram: null,
    },
    {
      name: 'age',
      type: 'numeric',
      null_count: 0,
      null_percentage: 0.0,
      unique_count: 92,
      is_pii: false,
      pii_type: null,
      pii_confidence: null,
      min: -5,
      max: 145,
      mean: 37.2,
      outliers_count: 20,
      histogram: {
        bins: ['<18', '18-30', '31-50', '51-70', '>70'],
        counts: [20, 380, 420, 150, 30],
      },
    },
    {
      name: 'city',
      type: 'string',
      null_count: 40,
      null_percentage: 4.0,
      unique_count: 35,
      is_pii: false,
      pii_type: null,
      pii_confidence: null,
      min: null,
      max: null,
      mean: null,
      outliers_count: 0,
      histogram: null,
    },
    {
      name: 'registration_date',
      type: 'datetime',
      null_count: 0,
      null_percentage: 0.0,
      unique_count: 520,
      is_pii: false,
      pii_type: null,
      pii_confidence: null,
      min: '2020-01-01',
      max: '2027-08-30',
      mean: null,
      outliers_count: 30,
      histogram: null,
    },
  ],
}

export async function mockDatasetProfile(id: number | string): Promise<DatasetProfileResponse> {
  await delay(350)
  const numId = Number(id)
  if (numId === 103) return mockCustomersProfile
  return { ...mockPayrollProfile, dataset_id: Number.isFinite(numId) && numId > 0 ? numId : 1 }
}
