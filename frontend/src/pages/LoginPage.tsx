import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { Field, PasswordField } from '../components/Field'
import { IconDatabase } from '../components/icons'
import { HOME_BY_ROLE } from '../layout/nav'

type Problem = null | 'invalid' | 'locked' | 'other'

export default function LoginPage() {
  const { token, role, login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<{ username?: string; password?: string }>({})
  const [problem, setProblem] = useState<Problem>(null)
  const [otherMessage, setOtherMessage] = useState('')
  const [loading, setLoading] = useState(false)

  if (token && role) return <Navigate to={HOME_BY_ROLE[role]} replace />

  const locked = problem === 'locked'
  const disabled = loading || locked

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const next: typeof errors = {}
    if (!username.trim()) next.username = 'Введіть логін'
    if (!password) next.password = 'Введіть пароль'
    setErrors(next)
    setProblem(null)
    if (Object.keys(next).length) return

    setLoading(true)
    try {
      const userRole = await login(username.trim(), password)
      navigate(HOME_BY_ROLE[userRole], { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setProblem('invalid') // UC-01, EX1
      else if (err instanceof ApiError && (err.status === 423 || err.status === 429)) setProblem('locked') // UC-01, EX2
      else {
        setProblem('other')
        setOtherMessage(err instanceof Error ? err.message : 'Не вдалося увійти. Спробуйте ще раз.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login">
      <div className="login__brand">
        <span className="login__logo" aria-hidden="true"><IconDatabase size={36} /></span>
        <span className="login__name">Data Clean Room</span>
        <span>Безпечна платформа обміну даними</span>
      </div>
      <div className="login__card">
        <h2>Вхід до системи</h2>
        <p className="login__lead">{loading ? 'Перевірка даних…' : 'Увійдіть, щоб продовжити роботу'}</p>
        <form className="login__form" onSubmit={handleSubmit} noValidate>
          <Field label="Логін" autoComplete="username" placeholder="Введіть логін" value={username} onChange={(e) => setUsername(e.target.value)} error={errors.username} invalid={problem === 'invalid'} disabled={disabled} />
          <PasswordField label="Пароль" autoComplete="current-password" placeholder="Введіть пароль" value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password} invalid={problem === 'invalid'} disabled={disabled} />
          {problem === 'invalid' && <Alert tone="error">Невірний логін або пароль</Alert>}
          {problem === 'locked' && (
            <Alert tone="warning" title="Вхід тимчасово недоступний">
              Через підозрілу активність вхід до системи тимчасово заблоковано. Зверніться до адміністратора або спробуйте пізніше.
            </Alert>
          )}
          {problem === 'other' && <Alert tone="error" title="Не вдалося увійти">{otherMessage}</Alert>}
          <Button type="submit" block disabled={locked} loading={loading} loadingText="Виконується вхід">Увійти</Button>
        </form>
        <p className="login__note">Доступ надається відповідно до ролі користувача</p>
      </div>
    </div>
  )
}
