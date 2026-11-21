import { EXCHANGE_STATUS_LABELS, STATUS_LABELS, type DataClass, type ExchangeRequestStatus, type VersionStatus } from '../api/types'
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

const EXCHANGE_STATUS_MOD: Record<string, string> = {
  pending: 'attention',
  Requested: 'attention',
  approved: 'published',
  Approved: 'published',
  rejected: 'expired',
  Rejected: 'expired',
  downloaded: 'uploaded',
  Downloaded: 'uploaded',
}

/** Статус запиту на обмін даними (UC-08 - UC-10). */
export function ExchangeStatusBadge({ value }: { value: ExchangeRequestStatus | string }) {
  const mod = EXCHANGE_STATUS_MOD[value] ?? 'attention'
  return (
    <span className={`badge badge--status badge--${mod}`}>
      <span className="badge__dot" aria-hidden="true" />
      {EXCHANGE_STATUS_LABELS[value] ?? value}
    </span>
  )
}

