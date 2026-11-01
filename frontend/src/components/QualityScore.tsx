/** Оцінка якості: число плюс підпис, щоб кольір не був єдиним носієм змісту. */
export function QualityScore({ score }: { score: number | null }) {
  if (score === null) return <span className="cell-muted">—</span>
  const level = score >= 80 ? 'high' : score >= 50 ? 'medium' : 'low'
  const label = level === 'high' ? 'Висока якість' : level === 'medium' ? 'Середня якість' : 'Низька якість'
  return (
    <span className={`quality quality--${level}`}>
      <span className="quality__score">{score} / 100</span>
      <small>{label}</small>
    </span>
  )
}
