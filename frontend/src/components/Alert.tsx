import type { ReactNode } from 'react'
import { IconAlert, IconCheckCircle, IconInfo, IconLock } from './icons'

type Tone = 'error' | 'warning' | 'info' | 'success'

interface AlertProps {
  tone?: Tone
  title?: string
  children?: ReactNode
}

export function Alert({ tone = 'error', title, children }: AlertProps) {
  const Icon = tone === 'warning' ? IconLock : tone === 'info' ? IconInfo : tone === 'success' ? IconCheckCircle : IconAlert
  return (
    <div className={`alert alert--${tone}`} role={tone === 'error' || tone === 'warning' ? 'alert' : 'status'}>
      <Icon />
      <div className="alert__body">
        {title && <span className="alert__title">{title}</span>}
        {children && <span>{children}</span>}
      </div>
    </div>
  )
}
