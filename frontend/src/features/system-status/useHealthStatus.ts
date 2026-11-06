import { useCallback, useEffect, useState } from 'react'
import { type ApiError, isAbortError, toApiError } from '@/shared/api/client'
import { fetchHealth, type HealthResponse } from './healthApi'

export type HealthState =
  | { phase: 'loading' }
  | { phase: 'ok'; data: HealthResponse; checkedAt: Date }
  | { phase: 'degraded'; data: HealthResponse; checkedAt: Date }
  | { phase: 'error'; error: ApiError; checkedAt: Date }

/** Gọi health khi trang mở và mỗi lần người dùng bấm "Kiểm tra lại". */
export function useHealthStatus() {
  const [state, setState] = useState<HealthState>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()

    fetchHealth(controller.signal)
      .then((data) => {
        setState({ phase: data.status === 'ok' ? 'ok' : 'degraded', data, checkedAt: new Date() })
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return // component bị gỡ hoặc đã có lần gọi mới
        setState({ phase: 'error', error: toApiError(error), checkedAt: new Date() })
      })

    return () => controller.abort()
  }, [attempt])

  const refresh = useCallback(() => {
    setState({ phase: 'loading' })
    setAttempt((n) => n + 1)
  }, [])

  return { state, refresh }
}
