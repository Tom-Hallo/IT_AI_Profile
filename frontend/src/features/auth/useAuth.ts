
import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '@/shared/api/client'
import { getCurrentUser, logout } from './api'
import type { AuthUser } from './types'

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isLoggingOut, setIsLoggingOut] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Kiểm tra trạng thái đăng nhập khi component được hiển thị
  useEffect(() => {
    let cancelled = false

    async function loadUser() {
      try {
        const currentUser = await getCurrentUser()

        if (!cancelled) {
          setUser(currentUser)
        }
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError && err.status === 401) {
            setUser(null)
          } else {
            setError('Không thể kiểm tra trạng thái đăng nhập.')
          }
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    void loadUser()

    return () => {
      cancelled = true
    }
  }, [])

  // Đăng xuất
  const signOut = useCallback(async () => {
    setIsLoggingOut(true)
    setError(null)

    try {
      await logout()
      setUser(null)
    } catch {
      setError('Đăng xuất thất bại. Vui lòng thử lại.')
    } finally {
      setIsLoggingOut(false)
    }
  }, [])

  return {
    user,
    isLoading,
    isLoggingOut,
    error,
    signOut,
  }
}
