import type { ReactNode } from 'react'
import { Alert } from './Alert'

export function ErrorMessage({ title, children }: { title?: string; children?: ReactNode }) {
  return <Alert tone="error" title={title}>{children}</Alert>
}
