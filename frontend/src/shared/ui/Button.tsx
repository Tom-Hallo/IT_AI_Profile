import type { ButtonHTMLAttributes } from 'react'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'primary' | 'ghost' | 'danger'
}

export function Button({
  variant = 'default',
  className = '',
  type = 'button',
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      type={type}
      className={[
        'btn',
        variant !== 'default' ? `btn--${variant}` : '',
        className,
      ].filter(Boolean).join(' ')}
    />
  )
}