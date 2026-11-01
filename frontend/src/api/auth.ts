import { config, endpoints } from '../config'
import { request } from './client'
import { mockLogin, mockMe } from './mock'
import type { LoginResponse, User } from './types'

/** `login` у формі = поле `email` у контракті C. Підтвердити, що це та сама сутність. */
export function login(email: string, password: string): Promise<LoginResponse> {
  if (config.useMock) return mockLogin(email, password)
  return request<LoginResponse>(endpoints.login, { method: 'POST', body: { email, password }, auth: false })
}

export function fetchMe(): Promise<User> {
  if (config.useMock) return mockMe()
  return request<User>(endpoints.me)
}
