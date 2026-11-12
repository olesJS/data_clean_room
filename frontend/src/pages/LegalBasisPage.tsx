import { Link, useParams } from 'react-router-dom'
import { LegalBasisPanel } from '../components/LegalBasisPanel'

export default function LegalBasisPage() {
  const { id } = useParams<{ id: string }>()
  const datasetId = id ?? ''

  return (
    <div className="qr-page">
      <div className="page-header page-header--row">
        <div className="page-header">
          <h1>Правові підстави</h1>
          <p className="subtitle">
            Набір №{datasetId}: реєстр згод, договорів і законних підстав для обробки та передачі
            даних.
          </p>
        </div>
        <div className="actions">
          <Link to={`/datasets/${datasetId}/publish`} className="btn btn--secondary">
            До публікації
          </Link>
          <Link to="/datasets" className="btn btn--secondary">
            До наборів
          </Link>
        </div>
      </div>

      <LegalBasisPanel datasetId={datasetId} />
    </div>
  )
}
