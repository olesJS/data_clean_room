import { useId, useState, type InputHTMLAttributes, type ReactNode } from 'react'
import { IconEye, IconEyeOff } from './icons'

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  error?: string
  /** Червона рамка без тексту під полем (коли помилку показує спільний блок). */
  invalid?: boolean
  end?: ReactNode
}

export function Field({ label, error, invalid, end, className = '', ...rest }: FieldProps) {
  const id = useId()
  const bad = Boolean(error) || invalid
  return (
    <div className={`field${bad ? ' field--error' : ''} ${className}`.trim()}>
      <label className="field__label" htmlFor={id}>{label}</label>
      <div className="field__control">
        <input id={id} className="field__input" aria-invalid={bad || undefined} aria-describedby={error ? `${id}-error` : undefined} {...rest} />
        {end && <span className="field__end">{end}</span>}
      </div>
      {error && <span id={`${id}-error`} className="field__error">{error}</span>}
    </div>
  )
}

/** Поле пароля з кнопкою «показати / сховати». */
export function PasswordField(props: Omit<FieldProps, 'type' | 'end'>) {
  const [visible, setVisible] = useState(false)
  return (
    <Field
      {...props}
      type={visible ? 'text' : 'password'}
      end={
        <button type="button" className="field__toggle" onClick={() => setVisible((v) => !v)} aria-label={visible ? 'Сховати пароль' : 'Показати пароль'} disabled={props.disabled}>
          {visible ? <IconEyeOff /> : <IconEye />}
        </button>
      }
    />
  )
}
