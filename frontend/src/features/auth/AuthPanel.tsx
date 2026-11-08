import { env } from '@/shared/config/env'
import { useAuth } from './useAuth'
import './AuthPanel.css'

export function AuthPanel() {
  const { user, isLoading, isLoggingOut, error, signOut } = useAuth()

  const handleGitHubLogin = () => {
    if (!env.apiBaseUrl) return

    window.location.assign(`${env.apiBaseUrl}/auth/github`)
  }

  return (
    <section className="auth-panel" aria-labelledby="auth-heading">
      <h2 id="auth-heading">Tài khoản</h2>

      {isLoading ? (
        <p role="status">Đang kiểm tra đăng nhập...</p>
      ) : user ? (
        <div className="auth-user">
          <p>
            Xin chào, <strong>{user.full_name}</strong>
          </p>

          <p>Email: {user.email}</p>

          <button
            type="button"
            className="button"
            onClick={() => void signOut()}
            disabled={isLoggingOut}
          >
            {isLoggingOut ? 'Đang đăng xuất...' : 'Đăng xuất'}
          </button>
        </div>
      ) : (
        <div>
          <p>Bạn chưa đăng nhập.</p>

          <button
            type="button"
            className="button"
            onClick={handleGitHubLogin}
            disabled={!env.apiBaseUrl}
          >
            Đăng nhập bằng GitHub
          </button>
        </div>
      )}

      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}

      {!env.apiBaseUrl && (
        <p className="auth-error" role="alert">
          Chưa cấu hình API URL.
        </p>
      )}
    </section>
  )
}