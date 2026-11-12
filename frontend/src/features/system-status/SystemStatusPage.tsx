import { Link } from 'react-router'
import { Button } from '@/shared/ui/Button'
import { env } from '@/shared/config/env'
import { AuthPanel } from '@/features/auth/AuthPanel'
import { useAuth } from '@/features/auth/useAuth'
import { GitHubRepositoriesSection } from '@/features/github/GitHubRepositoriesSection'
import { describeError } from './describeError'
import { type HealthState, useHealthStatus } from './useHealthStatus'
import './SystemStatusPage.css'

const CHECK_LABELS: Record<string, string> = {
  database: 'Cơ sở dữ liệu (PostgreSQL)',
  redis: 'Hàng đợi (Redis)',
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('vi-VN')
}

function BackendSummary({ state }: { state: HealthState }) {
  switch (state.phase) {
    case 'loading':
      return <span className="badge badge--pending">Đang kiểm tra…</span>
    case 'ok':
      return <span className="badge badge--ok">Hoạt động</span>
    case 'degraded':
      return <span className="badge badge--warn">Hoạt động nhưng có thành phần lỗi</span>
    case 'error':
      return <span className="badge badge--fail">Không kết nối được</span>
  }
}

export function SystemStatusPage() {
  const auth = useAuth()
  const { user } = auth
  const { state, refresh } = useHealthStatus()
  const isLoading = state.phase === 'loading'
  const data = state.phase === 'ok' || state.phase === 'degraded' ? state.data : null

  return (
    <main className="status-page">
      <header className="workspace-hero">
        <div>
          <h1>IT Talent AI Profile</h1>
          <p>Phân tích mã nguồn, hoạt động và đóng góp từ GitHub.</p>
        </div>
        <BackendSummary state={state} />
      </header>

      <AuthPanel auth={auth} />
      <p><Link to="/dashboard">Mở Dashboard hồ sơ</Link></p>

      {user && (
        <nav className="workspace-actions" aria-label="Công cụ phân tích">
          <Link to="/analysis" className="workspace-action">
            <strong>Phân tích mã nguồn</strong>
            <span>Ngôn ngữ, framework, kiến trúc và bằng chứng</span>
          </Link>
          <Link to="/activity" className="workspace-action">
            <strong>Phân tích hoạt động</strong>
            <span>Commit, pull request và đóng góp theo thời gian</span>
          </Link>
          <Link to="/role-scores" className="workspace-action">
            <strong>Điểm năng lực theo vai trò</strong>
            <span>Public, Private và Combined</span>
          </Link>
        </nav>
      )}

      <GitHubRepositoriesSection isAuthenticated={Boolean(user)} />

      <details className="card workspace-diagnostics">
        <summary>Chi tiết kết nối hệ thống</summary>

        <dl className="rows" aria-live="polite">
          <div className="row">
            <dt>Frontend</dt>
            <dd>
              <span className="badge badge--ok">Đang chạy</span>
            </dd>
          </div>

          <div className="row">
            <dt>Backend</dt>
            <dd>
              <BackendSummary state={state} />
            </dd>
          </div>

          {data &&
            Object.entries(data.checks).map(([name, result]) => (
              <div className="row row--sub" key={name}>
                <dt>{CHECK_LABELS[name] ?? name}</dt>
                <dd>
                  <span className={result === 'ok' ? 'badge badge--ok' : 'badge badge--fail'}>
                    {result === 'ok' ? 'Bình thường' : 'Lỗi'}
                  </span>
                </dd>
              </div>
            ))}

          {data && (
            <div className="row row--sub">
              <dt>Phiên bản Backend</dt>
              <dd>{data.version}</dd>
            </div>
          )}

          <div className="row">
            <dt>API base URL</dt>
            <dd>
              <code>{env.apiBaseUrl ?? '(chưa cấu hình)'}</code>
            </dd>
          </div>

          {state.phase !== 'loading' && (
            <div className="row">
              <dt>Kiểm tra lần cuối</dt>
              <dd>{formatTime(state.checkedAt)}</dd>
            </div>
          )}
        </dl>

        {state.phase === 'degraded' && (
          <p className="notice notice--warn" role="status">
            Backend đang chạy nhưng một thành phần phụ thuộc báo lỗi. Xem các dòng có nhãn “Lỗi” ở
            trên.
          </p>
        )}

        {state.phase === 'error' && (
          <div className="notice notice--fail" role="alert">
            <strong>{describeError(state.error).title}</strong>
            <p>{describeError(state.error).hint}</p>
          </div>
        )}

        <Button variant="primary" onClick={refresh} disabled={isLoading}>
          {isLoading ? 'Đang kiểm tra…' : 'Kiểm tra lại'}
        </Button>
      </details>
    </main>
  )
}
