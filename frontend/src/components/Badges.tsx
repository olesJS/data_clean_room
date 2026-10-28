import { STATUS_LABELS, type DataClass, type VersionStatus } from '../api/types'
import { IconShield } from './icons'

/** Клас даних: пігулка з іконкою щита. Колір темнішає зі зростанням чутливості. */
export function ClassBadge({ value }: { value: DataClass }) {
  return (
    <span className={`badge badge--class badge--${value.toLowerCase()}`}>
      <IconShield size={12} />
      {value}
    </span>
  )
}

const STATUS_MOD: Record<VersionStatus, string> = {
  Uploaded: 'uploaded',
  Profiled: 'profiled',
  'Needs attention': 'attention',
  Published: 'published',
  Expired: 'expired',
}

/** Статус версії: прямокутна мітка з крапкою (відрізняється від класу формою). */
export function StatusBadge({ value }: { value: VersionStatus }) {
  return (
    <span className={`badge badge--status badge--${STATUS_MOD[value]}`}>
      <span className="badge__dot" aria-hidden="true" />
      {STATUS_LABELS[value]}
    </span>
  )
}
