import { forwardRef } from 'react'
import type { InputHTMLAttributes } from 'react'

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  error?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  function Input(
    { label, error, id, className = '', ...props },
    ref,
  ) {
    const inputId = id ?? `input-${label.toLowerCase().replace(/\s+/g, '-')}`
    const errorId = `${inputId}-error`

    return (
      <div className="field">
        <label htmlFor={inputId}>{label}</label>

        <input
          {...props}
          ref={ref}
          id={inputId}
          className={['input', className].filter(Boolean).join(' ')}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? errorId : props['aria-describedby']}
        />

        {error && (
          <span id={errorId} className="field-error" role="alert">
            {error}
          </span>
        )}
      </div>
    )
  },
)