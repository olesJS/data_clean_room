import { createContext } from 'react'
import type { Role } from '../api/types'

export interface AuthState {
  token: string | null
  role: Role | null
  email: string | null
  /** false, поки перевіряємо збережений токен через GET /me */
  ready: boolean
  login: (email: string, password: string) => Promise<Role>
  logout: () => void
}

export const AuthContext = createContext<AuthState | null>(null)
