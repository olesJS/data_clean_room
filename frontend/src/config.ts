export const config = {
  /** Базова адреса API. Порожня = той самий origin (у dev працює проксі Vite). */
  apiUrl: (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, ''),
  /** true = заглушка замість бекенду (доки C і D не віддали API). */
  useMock: import.meta.env.VITE_USE_MOCK === 'true',
}

/** Максимальний розмір файлу, який перевіряє фронтенд до надсилання (як у макеті). */
export const MAX_UPLOAD_MB = 50

/** Шляхи API. Якщо бекенд змінить адреси, правка потрібна лише тут. */
export const endpoints = {
  login: '/api/auth/login',
  me: '/api/auth/me',
  datasets: '/api/datasets',
  datasetProfile: (id: number | string) => `/api/datasets/${id}/profile`,
  datasetPii: (id: number | string) => `/api/datasets/${id}/pii`,
  datasetPiiColumn: (id: number | string, col: string) => `/api/datasets/${id}/pii/${encodeURIComponent(col)}`,
  datasetQualityRules: (id: number | string) => `/api/datasets/${id}/quality-rules`,
  datasetQualityViolations: (id: number | string, action?: string) =>
    `/api/datasets/${id}/quality-violations${action ? `?action=${action}` : ''}`,
}
