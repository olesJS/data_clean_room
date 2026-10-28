import { Navigate, Outlet, useLocation } from 'react-router-dom'
import type { Role } from '../api/types'
import ForbiddenPage from '../pages/ForbiddenPage'
import { useAuth } from './useAuth'

/** Без токена переспрямовує на /login. */
export function RequireAuth() {
  const { token, ready } = useAuth()
  const location = useLocation()
  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (!ready) return <p className="subtitle" style={{ padding: 40 }}>Завантаження…</p>
  return <Outlet />
}

/** Пускає лише вказані ролі; для решти показує «Немає доступу». */
export function RequireRole({ allow }: { allow: Role[] }) {
  const { role } = useAuth()
  if (!role || !allow.includes(role)) return <ForbiddenPage />
  return <Outlet />
}
