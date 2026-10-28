import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { ROLE_LABELS } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { Button } from '../components/Button'
import { IconDatabase, IconLogOut } from '../components/icons'
import { NAV_ITEMS } from './nav'

export function AppLayout() {
  const { role, email, logout } = useAuth()
  const navigate = useNavigate()
  // Пункти, недоступні ролі, не показуємо.
  const items = NAV_ITEMS.filter((i) => role && i.roles.includes(role))

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__logo" aria-hidden="true"><IconDatabase size={20} /></span>
          Data Clean Room
        </div>
        <nav className="nav" aria-label="Головне меню">
          {items.map((i) => (
            <NavLink key={i.label} to={i.to} className={({ isActive }) => `nav__link${isActive ? ' is-active' : ''}`}>
              {i.label}
            </NavLink>
          ))}
        </nav>
        <div className="user">
          <span className="user__name">{email ?? 'Користувач'}</span>
          <span className="user__role">{role ? ROLE_LABELS[role] : ''}</span>
          <Button variant="on-dark" onClick={handleLogout}><IconLogOut /> Вийти</Button>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
