import type { HTMLAttributes } from 'react'

type CardProps = HTMLAttributes<HTMLElement> & {
  glass?: boolean
}

export function Card({
  glass = false,
  className = '',
  children,
  ...props
}: CardProps) {
  return (
    <section
      {...props}
      className={[
        'card',
        glass ? 'card--glass' : '',
        className,
      ].filter(Boolean).join(' ')}
    >
      {children}
    </section>
  )
}