import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { fetchMe, login as loginRequest } from '../api/auth'
import { setUnauthorizedHandler } from '../api/client'
import type { Role } from '../api/types'
import { AuthContext, type AuthState } from './AuthContext'
import { storage } from './storage'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(storage.getToken)
  const [role, setRole] = useState<Role | null>(storage.getRole)
  const [email, setEmail] = useState<string | null>(storage.getEmail)
  const [ready, setReady] = useState<boolean>(() => !storage.getToken())

  const logout = useCallback(() => {
    storage.clear()
    setToken(null)
    setRole(null)
    setEmail(null)
  }, [])

  // Відповідь 401 від будь-якого запиту: чистимо токен, ProtectedRoute поверне на /login.
  useEffect(() => {
    setUnauthorizedHandler(logout)
    return () => setUnauthorizedHandler(null)
  }, [logout])

  // При старті перевіряємо збережений токен.
  useEffect(() => {
    if (!storage.getToken()) return
    let cancelled = false
    fetchMe()
      .then((user) => {
        if (cancelled) return
        storage.setRole(user.role)
        setRole(user.role)
        setEmail(user.email)
      })
      .catch(() => {
        /* 401 обробляє глобальний обробник; інші помилки не розлогінюють */
      })
      .finally(() => {
        if (!cancelled) setReady(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (userEmail: string, password: string) => {
    const res = await loginRequest(userEmail, password)
    storage.save(res.access_token, res.role, userEmail)
    setToken(res.access_token)
    setRole(res.role)
    setEmail(userEmail)
    return res.role
  }, [])

  const value = useMemo<AuthState>(
    () => ({ token, role, email, ready, login, logout }),
    [token, role, email, ready, login, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
