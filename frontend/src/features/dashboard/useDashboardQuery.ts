import { useEffect, useState } from 'react'
import { apiFetch } from '@/shared/api/client'

type State<T> =
  | { phase: 'loading' }
  | { phase: 'ready'; data: T }
  | { phase: 'error' }

export function useDashboardQuery<T>(path: string) {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{ path: string; attempt: number; state: State<T> }>()
  useEffect(() => {
    const controller = new AbortController()
    void apiFetch<T>(path, { signal: controller.signal }).then(
      (data) => {
        if (!controller.signal.aborted) setResult({ path, attempt, state: { phase: 'ready', data } })
      },
      () => {
        if (!controller.signal.aborted) setResult({ path, attempt, state: { phase: 'error' } })
      },
    )
    return () => controller.abort()
  }, [path, attempt])
  const state: State<T> = result?.path === path && result.attempt === attempt
    ? result.state
    : { phase: 'loading' }
  return { state, retry: () => setAttempt((value) => value + 1) }
}
