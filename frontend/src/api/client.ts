import { config } from '../config'
import { storage } from '../auth/storage'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

let onUnauthorized: (() => void) | null = null
/** AuthProvider реєструє тут вихід із системи, який спрацьовує на кожну відповідь 401. */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}
export function notifyUnauthorized() {
  onUnauthorized?.()
}

/** Дістає текст помилки з відповіді FastAPI: { detail: string | [{ msg }] }. */
export function extractError(data: unknown, fallback: string): string {
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : ''))
        .filter(Boolean)
      if (msgs.length) return msgs.join('; ')
    }
  }
  return fallback
}

export const NETWORK_ERROR = 'Не вдалося зв’язатися із сервером. Перевірте підключення й спробуйте ще раз.'

interface RequestOptions {
  method?: string
  body?: unknown
  /** false для запитів без токена (логін). Тоді 401 не вважається завершенням сесії. */
  auth?: boolean
}

export async function request<T>(path: string, { method = 'GET', body, auth = true }: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const token = storage.getToken()
  if (auth && token) headers.Authorization = `Bearer ${token}`

  let res: Response
  try {
    res = await fetch(config.apiUrl + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(NETWORK_ERROR, 0)
  }

  const data: unknown = await res.json().catch(() => null)
  if (res.status === 401 && auth) notifyUnauthorized()
  if (!res.ok) throw new ApiError(extractError(data, `Помилка сервера (${res.status})`), res.status)
  return data as T
}
