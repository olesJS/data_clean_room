import type { ButtonHTMLAttributes } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'on-dark' | 'danger-soft'
  block?: boolean
  loading?: boolean
  /** Текст на кнопці під час завантаження */
  loadingText?: string
}

export function Button({ variant = 'primary', block, loading, loadingText = 'Зачекайте…', disabled, className = '', children, type = 'button', ...rest }: ButtonProps) {
  const cls = ['btn', variant !== 'primary' && `btn--${variant}`, block && 'btn--block', className].filter(Boolean).join(' ')
  return (
    <button type={type} className={cls} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? loadingText : children}
    </button>
  )
}
