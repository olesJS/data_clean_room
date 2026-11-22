import { ApiError } from './client'
import type {
  AnonymizationColumn,
  AnonymizationMethodName,
  AnonymizationPreview,
  AnonymizationPreviewRow,
  AnonymizedVersion,
  CatalogItem,
  DataClass,
  DatasetProfileResponse,
  DatasetVersion,
  ExchangeRequest,
  LegalBasis,
  LegalBasisCreatePayload,
  LoginResponse,
  PiiFinding,
  PiiScanResponse,
  PiiType,
  PiiUpdatePayload,
  QualityReport,
  QualityRule,
  QualityViolation,
  Role,
  UploadResult,
  User,
} from './types'
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

// ─── PII scan mock data ───────────────────────────────────────────────────────

const piiFindings: Record<number, PiiFinding[]> = {
  101: [
    {
      column_name: 'ipn',
      pii_type: 'ipn',
      confidence: 0.98,
      sample_masked: '12345*****',
      detection_method: 'regex+checksum',
      user_confirmed: null,
    },
    {
      column_name: 'full_name',
      pii_type: 'person_name',
      confidence: 0.95,
      sample_masked: 'Іван П***',
      detection_method: 'dictionary',
      user_confirmed: null,
    },
    {
      column_name: 'iban',
      pii_type: 'iban',
      confidence: 0.99,
      sample_masked: 'UA21 3220 ****',
      detection_method: 'regex+checksum',
      user_confirmed: null,
    },
  ],
  103: [
    {
      column_name: 'full_name',
      pii_type: 'person_name',
      confidence: 0.94,
      sample_masked: 'Марія К***',
      detection_method: 'dictionary',
      user_confirmed: null,
    },
    {
      column_name: 'email',
      pii_type: 'email',
      confidence: 0.99,
      sample_masked: 'm***@example.com',
      detection_method: 'regex',
      user_confirmed: null,
    },
    {
      column_name: 'phone',
      pii_type: 'phone',
      confidence: 0.98,
      sample_masked: '+380 67 ***-**-11',
      detection_method: 'regex',
      user_confirmed: null,
    },
    {
      column_name: 'birth_date',
      pii_type: 'birth_date',
      confidence: 0.92,
      sample_masked: '198*-**-**',
      detection_method: 'column_name+regex',
      user_confirmed: null,
    },
    {
      column_name: 'ipn',
      pii_type: 'ipn',
      confidence: 0.96,
      sample_masked: '98765*****',
      detection_method: 'regex+checksum',
      user_confirmed: null,
    },
  ],
}

export async function mockPiiScan(id: number | string): Promise<PiiScanResponse> {
  await delay(350)
  const numId = Number(id)
  if (numId === 103) {
    return {
      dataset_id: 103,
      dataset_name: 'customers.json',
      data_class: 'Personal',
      pii_columns_count: 5,
      total_columns: 8,
      findings: piiFindings[103].map((f) => ({ ...f })),
    }
  }
  return {
    dataset_id: numId > 0 ? numId : 1,
    dataset_name: 'payroll.csv',
    data_class: 'Personal',
    pii_columns_count: 3,
    total_columns: 6,
    findings: piiFindings[101].map((f) => ({ ...f })),
  }
}

export async function mockPiiUpdate(
  _id: number | string,
  columnName: string,
  payload: PiiUpdatePayload
): Promise<PiiFinding> {
  await delay(300)
  const numId = Number(_id)
  const list = numId === 103 ? piiFindings[103] : piiFindings[101]
  const idx = list.findIndex((f) => f.column_name === columnName)
  if (idx === -1) throw new ApiError('Колонку не знайдено', 404)
  list[idx] = {
    ...list[idx],
    user_confirmed: payload.user_confirmed,
    corrected_pii_type: payload.corrected_pii_type ?? list[idx].corrected_pii_type,
    pii_type: (payload.corrected_pii_type !== undefined
      ? payload.corrected_pii_type
      : list[idx].pii_type) as PiiType,
  }
  return { ...list[idx] }
}

// ─── Quality Rules & Violations mock data (SCRUM-49) ──────────────────────────

type QualityScenario = 'payroll' | 'customers' | 'blocked' | 'empty'

const violation = (
  column: string,
  condition: string,
  action: QualityViolation['action'],
  count: number,
): QualityViolation => ({
  column,
  condition,
  action,
  violation_count: count,
  is_blocking: action === 'block' && count > 0,
})

const duplicateRule: QualityRule = {
  column: '*',
  condition: 'not_duplicated',
  action: 'flag',
  description: 'Повні копії рядків (друге й наступні входження)',
}

const payrollRules: QualityRule[] = [
  { column: 'amount_uah', condition: '> 0', action: 'reject', description: 'Сума виплати повинна бути більшою за 0' },
  { column: 'payment_date', condition: '<= today', action: 'reject', description: 'Дата виплати не може бути в майбутньому' },
  { column: 'ipn', condition: 'not_null', action: 'flag', description: 'ІПН не повинен бути порожнім' },
  duplicateRule,
]

const customersRules: QualityRule[] = [
  { column: 'age', condition: 'between(0, 120)', action: 'reject', description: 'Вік має бути від 0 до 120 років' },
  { column: 'registration_date', condition: '<= today', action: 'reject', description: 'Дата реєстрації не може бути в майбутньому' },
  { column: 'email', condition: 'email', action: 'flag', description: 'Електронна пошта повинна мати коректний формат' },
  { column: 'city', condition: 'not_null', action: 'flag', description: 'Місто не повинно бути порожнім' },
  duplicateRule,
]

const payrollReport: QualityReport = {
  dataset_id: 1,
  score: 91.8,
  total_rows: 500,
  unique_violating_rows: 41,
  can_publish: true,
  has_blocking_violations: false,
  action_counts: { reject: 16, flag: 25, block: 0 },
  summary: { duplicate_rows_count: 10 },
  violations: [
    violation('amount_uah', '> 0', 'reject', 8),
    violation('payment_date', '<= today', 'reject', 8),
    violation('ipn', 'not_null', 'flag', 15),
    violation('*', 'not_duplicated', 'flag', 10),
  ],
}

const customersReport: QualityReport = {
  dataset_id: 2,
  score: 87.0,
  total_rows: 1000,
  unique_violating_rows: 130,
  can_publish: true,
  has_blocking_violations: false,
  action_counts: { reject: 50, flag: 80, block: 0 },
  summary: { duplicate_rows_count: 15 },
  violations: [
    violation('age', 'between(0, 120)', 'reject', 20),
    violation('registration_date', '<= today', 'reject', 30),
    violation('email', 'email', 'flag', 25),
    violation('city', 'not_null', 'flag', 40),
    violation('*', 'not_duplicated', 'flag', 15),
  ],
}

const blockedReport: QualityReport = {
  ...payrollReport,
  can_publish: false,
  has_blocking_violations: true,
  action_counts: { reject: 16, flag: 25, block: 3 },
  violations: [...payrollReport.violations, violation('iban', 'iban_ua', 'block', 3)],
}

const emptyReport: QualityReport = {
  dataset_id: 3,
  score: 100,
  total_rows: 300,
  unique_violating_rows: 0,
  can_publish: true,
  has_blocking_violations: false,
  action_counts: { reject: 0, flag: 0, block: 0 },
  summary: { duplicate_rows_count: 0 },
  violations: [],
}

function qualityScenario(): QualityScenario {
  const name = new URLSearchParams(window.location.search).get('mock')
  return name === 'customers' || name === 'blocked' || name === 'empty' ? name : 'payroll'
}

export async function mockQualityRules(datasetId?: number | string): Promise<QualityRule[]> {
  await delay(400)
  const scenario = qualityScenario()
  const numId = Number(datasetId)
  if (scenario === 'customers' || numId === 2 || numId === 103) return customersRules
  if (scenario === 'blocked') {
    return [
      ...payrollRules.slice(0, 3),
      { column: 'iban', condition: 'iban_ua', action: 'block', description: 'IBAN має відповідати формату UA' },
      duplicateRule,
    ]
  }
  return payrollRules
}

export async function mockQualityReport(datasetId?: number | string): Promise<QualityReport> {
  await delay(400)
  const scenario = qualityScenario()
  const numId = Number(datasetId)
  if (scenario === 'customers' || numId === 2 || numId === 103) return customersReport
  if (scenario === 'blocked') return blockedReport
  if (scenario === 'empty') return emptyReport
  return payrollReport
}

// ─── Sprint 3: Mock анонімізації «до/після» (UC-06, SCRUM-61) ─────────────────

const sampleCustomerRows: Array<Record<string, string>> = [
  { id: '1', full_name: 'Олександр Коваленко', email: 'o.kovalenko@example.com', phone: '+380501234567', birth_date: '1988-04-12', ipn: '2847101234' },
  { id: '2', full_name: 'Марія Мельник', email: 'm.melnyk@example.com', phone: '+380672345678', birth_date: '1992-09-23', ipn: '3386902345' },
  { id: '3', full_name: 'Андрій Шевченко', email: 'a.shevchenko@example.com', phone: '+380933456789', birth_date: '1985-11-05', ipn: '3135503456' },
  { id: '4', full_name: 'Олена Бойко', email: 'o.boyko@example.com', phone: '+380504567890', birth_date: '1995-02-18', ipn: '3474904567' },
  { id: '5', full_name: 'Дмитро Кравченко', email: 'd.kravchenko@example.com', phone: '+380685678901', birth_date: '1980-07-30', ipn: '2943205678' },
  { id: '6', full_name: 'Тетяна Бондаренко', email: 't.bondarenko@example.com', phone: '+380736789012', birth_date: '1991-12-14', ipn: '3358606789' },
  { id: '7', full_name: 'Сергій Ткаченко', email: 's.tkachenko@example.com', phone: '+380957890123', birth_date: '1987-03-22', ipn: '3185907890' },
  { id: '8', full_name: 'Юлія Мороз', email: 'y.moroz@example.com', phone: '+380668901234', birth_date: '1994-08-09', ipn: '3455408901' },
  { id: '9', full_name: 'Володимир Лисенко', email: 'v.lysenko@example.com', phone: '+380979012345', birth_date: '1983-06-17', ipn: '3048409012' },
  { id: '10', full_name: 'Наталія Руденко', email: 'n.rudenko@example.com', phone: '+380500123456', birth_date: '1990-10-01', ipn: '3314600123' },
]

const samplePayrollRows: Array<Record<string, string>> = [
  { id: '1', full_name: 'Іван Петренко', birth_date: '1985-05-14', ipn: '3118101234', salary: '45000' },
  { id: '2', full_name: 'Ольга Сидоренко', birth_date: '1990-11-20', ipn: '3320202345', salary: '52000' },
  { id: '3', full_name: 'Василь Козак', birth_date: '1979-03-08', ipn: '2892103456', salary: '61000' },
  { id: '4', full_name: 'Анна Гончар', birth_date: '1993-07-25', ipn: '3417404567', salary: '48000' },
  { id: '5', full_name: 'Михайло Павленко', birth_date: '1982-12-11', ipn: '3029605678', salary: '55000' },
  { id: '6', full_name: 'Катерина Савченко', birth_date: '1996-01-19', ipn: '3508206789', salary: '42000' },
  { id: '7', full_name: 'Роман Клименко', birth_date: '1988-09-04', ipn: '3238907890', salary: '59000' },
  { id: '8', full_name: 'Світлана Дорошенко', birth_date: '1991-04-16', ipn: '3334308901', salary: '47000' },
  { id: '9', full_name: 'Ярослав Кузьменко', birth_date: '1984-10-28', ipn: '3098209012', salary: '64000' },
  { id: '10', full_name: 'Дарина Марченко', birth_date: '1997-08-03', ipn: '3564500123', salary: '41000' },
]

function pseudoHmac(val: string): string {
  let hash = 0
  for (let i = 0; i < val.length; i++) {
    hash = (hash << 5) - hash + val.charCodeAt(i)
    hash |= 0
  }
  const hex = Math.abs(hash).toString(16).padStart(8, '0')
  return `${hex}e49b81f2...`
}

export function transformValue(value: string | undefined, method: AnonymizationMethodName, piiType?: string): string {
  if (value === undefined || value === null || value === '') return ''
  switch (method) {
    case 'mask':
      return '***'
    case 'generalize': {
      if (piiType === 'birth_date' || /^\d{4}-\d{2}-\d{2}$/.test(value)) {
        return value.slice(0, 4)
      }
      if (/^\d+$/.test(value)) {
        const num = parseInt(value, 10)
        const bucket = Math.floor(num / 10) * 10
        return `${bucket}-${bucket + 9}`
      }
      return `${value.slice(0, 1)}***`
    }
    case 'hmac':
      return pseudoHmac(value)
    case 'redact':
      return '[ВИДАЛЕНО]'
    default:
      return value
  }
}

export async function mockPreviewAnonymization(
  datasetId: number | string,
  methods: Record<string, AnonymizationMethodName>,
): Promise<AnonymizationPreview> {
  await delay(450)
  const numId = Number(datasetId)
  const isCustomer = numId === 103 || numId === 2
  const findingsList = piiFindings[isCustomer ? 103 : 101] ?? []
  const baseRows = isCustomer ? sampleCustomerRows : samplePayrollRows

  const columns: AnonymizationColumn[] = findingsList.map((f) => ({
    column_name: f.column_name,
    pii_type: f.pii_type ?? 'person_name',
    method: methods[f.column_name] ?? 'mask',
  }))

  const methodCounts: Record<string, number> = { mask: 0, generalize: 0, hmac: 0, redact: 0 }
  for (const c of columns) {
    methodCounts[c.method] = (methodCounts[c.method] ?? 0) + 1
  }

  let estimatedClass: DataClass = 'Internal'
  if (columns.length > 0) {
    const hasHmac = columns.some((c) => c.method === 'hmac')
    estimatedClass = hasHmac ? 'Personal' : 'Confidential'
  }

  const piiTypeMap = new Map(findingsList.map((f) => [f.column_name, f.pii_type ?? '']))

  const previewPairs: AnonymizationPreviewRow[] = baseRows.map((row, idx) => {
    const orig: Record<string, string> = {}
    const anon: Record<string, string> = {}

    for (const [key, val] of Object.entries(row)) {
      orig[key] = val
      const method = methods[key]
      if (method) {
        anon[key] = transformValue(val, method, piiTypeMap.get(key))
      } else {
        anon[key] = val
      }
    }

    return {
      row_index: idx + 1,
      original: orig,
      anonymized: anon,
    }
  })

  return {
    dataset_id: Number(datasetId),
    dataset_name: isCustomer ? 'customers.json' : 'payroll.csv',
    pii_columns_count: columns.length,
    estimated_class: estimatedClass,
    hmac_requires_legal_basis: columns.some((c) => c.method === 'hmac'),
    method_counts: methodCounts,
    columns,
    preview_pairs: previewPairs,
  }
}

export async function mockApplyAnonymization(
  datasetId: number | string,
  methods: Record<string, AnonymizationMethodName>,
): Promise<AnonymizedVersion> {
  await delay(600)
  const numId = Number(datasetId)
  const isCustomer = numId === 103 || numId === 2
  const hasHmac = Object.values(methods).includes('hmac')

  return {
    dataset_id: Number(datasetId),
    version_id: 2,
    version_number: 2,
    kind: 'clean',
    file_name: isCustomer ? 'customers_clean.json' : 'payroll_clean.csv',
    row_count: isCustomer ? 300 : 500,
    sha256: '4f83b28b7a32c256a847e096f26487968565c404cf755d57b1ac656f4d0d0246',
    data_class: hasHmac ? 'Personal' : 'Confidential',
    created_at: new Date().toISOString(),
  }
}

// ─── Sprint 3: Mock каталогу, запитів на обмін та правових підстав (UC-08 – UC-12) ─

export const mockCatalogData: CatalogItem[] = [
  {
    id: 101,
    name: 'payroll_clean.csv',
    data_class: 'Personal',
    row_count: 500,
    quality_score: 96,
    anonymization_methods: [
      { column: 'ipn', method: 'hmac' },
      { column: 'birth_date', method: 'generalize' },
    ],
    uploaded_by: 'provider@example.com',
    created_at: '2026-11-20T12:00:00Z',
    retention_until: '2027-12-31',
    column_count: 5,
  },
  {
    id: 103,
    name: 'customers_clean.json',
    data_class: 'Confidential',
    row_count: 300,
    quality_score: 94,
    anonymization_methods: [
      { column: 'email', method: 'mask' },
      { column: 'phone', method: 'mask' },
    ],
    uploaded_by: 'provider@example.com',
    created_at: '2026-11-21T09:30:00Z',
    retention_until: '2028-06-30',
    column_count: 6,
  },
  {
    id: 105,
    name: 'store_catalog.csv',
    data_class: 'Public',
    row_count: 1200,
    quality_score: 99,
    anonymization_methods: [],
    uploaded_by: 'provider@example.com',
    created_at: '2026-11-21T15:00:00Z',
    retention_until: '2029-01-01',
    column_count: 8,
  },
]

export const mockLegalBasesStore: Record<number, LegalBasis[]> = {
  101: [
    {
      id: 'lb-101-1',
      dataset_id: 101,
      type: 'consent',
      document_ref: 'Згода суб’єктів персональних даних №101/2026',
      date: '2026-11-01',
      purpose: 'analytics',
      valid_until: '2027-12-31',
      entered_by: 1,
      created_at: '2026-11-01T10:00:00Z',
      revoked_at: null,
      revoked_by: null,
      revoked_reason: null,
      is_active: true,
    },
  ],
  103: [
    {
      id: 'lb-103-1',
      dataset_id: 103,
      type: 'contract',
      document_ref: 'Договір приєднання на обробку №К-45',
      date: '2026-10-15',
      purpose: 'research',
      valid_until: '2028-06-30',
      entered_by: 1,
      created_at: '2026-10-15T12:00:00Z',
      revoked_at: null,
      revoked_by: null,
      revoked_reason: null,
      is_active: true,
    },
  ],
}

export const mockRequestsStore: ExchangeRequest[] = [
  {
    id: 1,
    dataset_id: 101,
    dataset_name: 'payroll_clean.csv',
    dataset_class: 'Personal',
    consumer_id: 2,
    consumer_email: 'consumer@example.com',
    purpose: 'analytics',
    status: 'approved',
    review_comment: 'Погоджено для квартального фінансового аналізу',
    created_at: '2026-11-21T10:00:00Z',
    reviewed_at: '2026-11-21T11:00:00Z',
  },
  {
    id: 2,
    dataset_id: 103,
    dataset_name: 'customers_clean.json',
    dataset_class: 'Confidential',
    consumer_id: 2,
    consumer_email: 'consumer@example.com',
    purpose: 'research',
    status: 'pending',
    review_comment: null,
    created_at: '2026-11-21T14:30:00Z',
    reviewed_at: null,
  },
  {
    id: 3,
    dataset_id: 101,
    dataset_name: 'payroll_clean.csv',
    dataset_class: 'Personal',
    consumer_id: 3,
    consumer_email: 'analyst@example.com',
    purpose: 'publication',
    status: 'rejected',
    review_comment: 'Відхилено: публікація персональних даних заборонена',
    created_at: '2026-11-20T08:00:00Z',
    reviewed_at: '2026-11-20T09:15:00Z',
  },
]

export async function mockCatalog(): Promise<CatalogItem[]> {
  await delay(300)
  return [...mockCatalogData]
}

export async function mockExchangeRequests(): Promise<ExchangeRequest[]> {
  await delay(350)
  const role = storage.getRole()
  const email = storage.getEmail()

  if (role === 'DataConsumer') {
    return mockRequestsStore.filter(
      (r) => r.consumer_email === (email ?? 'consumer@example.com'),
    )
  }
  return [...mockRequestsStore]
}

export async function mockCreateExchangeRequest(
  datasetId: number,
  purpose: string,
): Promise<ExchangeRequest> {
  await delay(400)
  const email = storage.getEmail() ?? 'consumer@example.com'
  const catalogItem = mockCatalogData.find((d) => d.id === datasetId)

  // Перевірка на дублювання активного запиту
  const exists = mockRequestsStore.find(
    (r) =>
      r.dataset_id === datasetId &&
      r.consumer_email === email &&
      (r.status === 'pending' || r.status === 'Requested'),
  )
  if (exists) {
    throw new ApiError('Активний запит на цей набір уже існує', 409)
  }

  const newReq: ExchangeRequest = {
    id: mockRequestsStore.length + 1,
    dataset_id: datasetId,
    dataset_name: catalogItem?.name ?? `dataset-${datasetId}`,
    dataset_class: catalogItem?.data_class ?? 'Internal',
    consumer_id: 2,
    consumer_email: email,
    purpose,
    status: 'pending',
    review_comment: null,
    created_at: new Date().toISOString(),
    reviewed_at: null,
  }

  mockRequestsStore.unshift(newReq)
  return newReq
}

export async function mockApproveExchangeRequest(
  id: number,
  comment?: string,
): Promise<ExchangeRequest> {
  await delay(400)
  const req = mockRequestsStore.find((r) => r.id === id)
  if (!req) {
    throw new ApiError('Запит не знайдено', 404)
  }

  // Перевірка чинності правової підстави
  const bases = mockLegalBasesStore[req.dataset_id] ?? []
  const hasActiveBasis = bases.some(
    (b) =>
      b.is_active &&
      !b.revoked_at &&
      (b.purpose.toLowerCase() === req.purpose.toLowerCase() ||
        req.purpose.toLowerCase().includes(b.purpose.toLowerCase())),
  )

  const isRevoked = bases.some((b) => b.revoked_at !== null)

  if (!hasActiveBasis) {
    const reason = isRevoked
      ? 'revoked'
      : bases.length === 0
        ? 'no_legal_basis'
        : 'purpose_mismatch'
    throw new ApiError(`Cannot approve request: legal basis invalid (${reason})`, 409)
  }

  req.status = 'approved'
  req.review_comment = comment ?? 'Схвалено'
  req.reviewed_at = new Date().toISOString()
  return { ...req }
}

export async function mockRejectExchangeRequest(
  id: number,
  comment?: string,
): Promise<ExchangeRequest> {
  await delay(400)
  const req = mockRequestsStore.find((r) => r.id === id)
  if (!req) {
    throw new ApiError('Запит не знайдено', 404)
  }

  req.status = 'rejected'
  req.review_comment = comment ?? 'Відхилено'
  req.reviewed_at = new Date().toISOString()
  return { ...req }
}

export async function mockDownloadExchangeFile(
  id: number,
  fallbackName = 'clean_dataset.csv',
): Promise<void> {
  await delay(500)
  const req = mockRequestsStore.find((r) => r.id === id)
  if (!req) {
    throw new ApiError('Запит не знайдено', 404)
  }

  if (req.status !== 'approved' && req.status !== 'Approved' && req.status !== 'downloaded') {
    throw new ApiError(`Завантаження неможливе для статусу ${req.status}`, 403)
  }

  // Перевірка чи не відкликана підстава
  const bases = mockLegalBasesStore[req.dataset_id] ?? []
  const isRevoked = bases.some((b) => b.revoked_at !== null)
  if (isRevoked) {
    throw new ApiError('Згоду або правову підставу відкликано — завантаження неможливе.', 403)
  }

  req.status = 'downloaded'

  // Створення зразка файлу у браузері
  const content = `id,name,value\n1,Sample_Clean_1,***\n2,Sample_Clean_2,***\n`
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fallbackName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export async function mockLegalBasis(datasetId: number | string): Promise<LegalBasis[]> {
  await delay(300)
  const numId = Number(datasetId)
  if (!mockLegalBasesStore[numId]) {
    mockLegalBasesStore[numId] = [
      {
        id: `lb-${numId}-1`,
        dataset_id: numId,
        type: 'consent',
        document_ref: `Згода на обробку персональних даних для набору #${numId}`,
        date: new Date().toISOString().slice(0, 10),
        purpose: 'analytics',
        valid_until: '2027-12-31',
        entered_by: 1,
        created_at: new Date().toISOString(),
        revoked_at: null,
        revoked_by: null,
        revoked_reason: null,
        is_active: true,
      },
    ]
  }
  return [...mockLegalBasesStore[numId]]
}

export async function mockCreateLegalBasis(
  datasetId: number | string,
  payload: LegalBasisCreatePayload,
): Promise<LegalBasis> {
  await delay(400)
  const numId = Number(datasetId)
  const entry: LegalBasis = {
    id: `lb-${numId}-${Date.now()}`,
    dataset_id: numId,
    type: payload.type,
    document_ref: payload.document_ref,
    date: payload.date,
    purpose: payload.purpose,
    valid_until: payload.valid_until ?? null,
    entered_by: 1,
    created_at: new Date().toISOString(),
    revoked_at: null,
    revoked_by: null,
    revoked_reason: null,
    is_active: true,
  }
  if (!mockLegalBasesStore[numId]) mockLegalBasesStore[numId] = []
  mockLegalBasesStore[numId].unshift(entry)
  return entry
}

export async function mockRevokeLegalBasis(
  id: string,
  reason: string,
): Promise<LegalBasis> {
  await delay(400)
  for (const list of Object.values(mockLegalBasesStore)) {
    const found = list.find((item) => item.id === id)
    if (found) {
      found.revoked_at = new Date().toISOString()
      found.revoked_by = 1
      found.revoked_reason = reason
      found.is_active = false
      return { ...found }
    }
  }
  throw new ApiError('Правову підставу не знайдено', 404)
}
