type LoadingStateProps = {
  message: string
  variant?: 'card' | 'rows' | 'inline'
}

export function LoadingState({ message, variant = 'card' }: LoadingStateProps) {
  return (
    <div className={`ita-app-loading ita-app-loading--${variant}`} role="status">
      {variant === 'inline' ? (
        <>
          <span className="ita-app-spinner" aria-hidden="true" />
          <span className="ita-app-loading-message">{message}</span>
        </>
      ) : (
        <>
          <span className="ita-app-loading-message">{message}</span>
          <div className="ita-app-skeleton-stack" aria-hidden="true">
            <span className="ita-app-skeleton-line" />
            <span className="ita-app-skeleton-line" />
            <span className="ita-app-skeleton-line" />
          </div>
        </>
      )}
    </div>
  )
}
