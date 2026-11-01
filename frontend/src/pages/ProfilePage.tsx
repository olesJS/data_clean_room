import { useParams } from 'react-router-dom'
import { StubPage } from '../components/StubPage'

export default function ProfilePage() {
  const { id } = useParams()
  return <StubPage title="Профіль набору та Quality Score" note={`UC-03 · набір ${id ?? ''}`} />
}
