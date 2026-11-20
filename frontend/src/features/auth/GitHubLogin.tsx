import { useState } from 'react'
import { ApiError, apiFetch } from '@/shared/api/client'
import { env } from '@/shared/config/env'

export function GitHubLogin() {
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function login() {
    setLoading(true)
    setError('')
    try {
      await apiFetch('/auth/github/status')
      window.location.assign(`${env.apiBaseUrl}/auth/github`)
    } catch (err) {
      const detail = err instanceof ApiError && typeof err.body === 'object' && err.body
        && 'detail' in err.body && typeof err.body.detail === 'string' ? err.body.detail : null
      setError(detail ?? (err instanceof Error ? err.message : 'Không thể kết nối GitHub.'))
      setLoading(false)
    }
  }

  return <div className="github-login">
    <button className="pixel-topbar-chat" type="button" disabled={loading || !env.apiBaseUrl} onClick={() => void login()}>
      {loading ? 'Đang mở GitHub…' : 'Đăng nhập bằng GitHub'}
    </button>
    {error && <p role="alert">{error}</p>}
  </div>
}
