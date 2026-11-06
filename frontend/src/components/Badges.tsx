import { STATUS_LABELS, type DataClass, type VersionStatus } from '../api/types'
import { IconShield } from './icons'

/** Клас даних: пігулка з іконкою щита. Колір темнішає зі зростанням чутливості. */
export function ClassBadge({ value }: { value?: DataClass }) {
  const safeVal = value || 'Internal'
  return (
    <span className={`badge badge--class badge--${safeVal.toLowerCase()}`}>
      <IconShield size={12} />
      {safeVal}
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
export function StatusBadge({ value }: { value?: VersionStatus }) {
  const safeVal = value || 'Uploaded'
  return (
    <span className={`badge badge--status badge--${STATUS_MOD[safeVal] || 'uploaded'}`}>
      <span className="badge__dot" aria-hidden="true" />
      {STATUS_LABELS[safeVal] || safeVal}
    </span>
  )
}
