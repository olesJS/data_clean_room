import type { Role } from '../api/types'

export interface NavItem {
  label: string
  to: string
  roles: Role[]
}

// Назви пунктів збігаються з макетом Figma (екран «Навігація за ролями»).
export const NAV_ITEMS: NavItem[] = [
  { label: 'Мої набори даних', to: '/datasets', roles: ['DataProvider'] },
  { label: 'Імпортувати дані', to: '/upload', roles: ['DataProvider'] },
  { label: 'Запити на доступ', to: '/access', roles: ['DataProvider'] },
  { label: 'Каталог', to: '/catalog', roles: ['DataConsumer'] },
  { label: 'Мої запити', to: '/requests', roles: ['DataConsumer'] },
  { label: 'Каталог (метадані)', to: '/catalog', roles: ['DataSteward'] },
  { label: 'Журнал аудиту', to: '/audit', roles: ['DataSteward'] },
]

/** Куди потрапляє користувач після входу. */
export const HOME_BY_ROLE: Record<Role, string> = {
  DataProvider: '/datasets',
  DataConsumer: '/catalog',
  DataSteward: '/audit',
}
