import type { Role } from '../api/types'

const TOKEN_KEY = 'dcr_token'
const ROLE_KEY = 'dcr_role'
const EMAIL_KEY = 'dcr_email'

// Для прототипу токен лежить у localStorage (так вимагає завдання).
export const storage = {
  getToken: () => localStorage.getItem(TOKEN_KEY),
  getRole: () => localStorage.getItem(ROLE_KEY) as Role | null,
  getEmail: () => localStorage.getItem(EMAIL_KEY),
  save(token: string, role: Role, email: string) {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(ROLE_KEY, role)
    localStorage.setItem(EMAIL_KEY, email)
  },
  setRole(role: Role) { localStorage.setItem(ROLE_KEY, role) },
  clear() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(ROLE_KEY)
    localStorage.removeItem(EMAIL_KEY)
  },
}
