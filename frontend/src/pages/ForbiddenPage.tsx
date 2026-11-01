import { Link } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { ErrorMessage } from '../components/ErrorMessage'
import { PageHeader } from '../components/PageHeader'
import { HOME_BY_ROLE } from '../layout/nav'

export default function ForbiddenPage() {
  const { role } = useAuth()
  return (
    <>
      <PageHeader title="Немає доступу" />
      <ErrorMessage title="Немає доступу">Ця сторінка недоступна для вашої ролі.</ErrorMessage>
      {role && <Link className="btn btn--secondary" style={{ alignSelf: 'flex-start' }} to={HOME_BY_ROLE[role]}>На головну</Link>}
    </>
  )
}
