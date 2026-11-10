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
  const { user } = useAuth()
  const { state, refresh } = useHealthStatus()
  const isLoading = state.phase === 'loading'
  const data = state.phase === 'ok' || state.phase === 'degraded' ? state.data : null

  return (
    <main className="status-page">
      <header>
        <h1>IT Talent AI Profile</h1>
        <p className="subtitle">Trang kiểm tra hệ thống</p>
      </header>

      <AuthPanel />

      {user && (
        <>
          <section className="card" style={{ marginBottom: '1rem', background: '#f0fdf4', borderColor: '#bbf7d0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
              <div>
                <h2 style={{ fontSize: '1.15rem', margin: '0 0 4px', color: '#166534' }}>
                  📊 Phân tích hoạt động GitHub (PBI-010)
                </h2>
                <p style={{ margin: 0, fontSize: '0.9rem', color: '#15803d' }}>
                  Phân tích commits và pull requests theo khoảng thời gian thực tế từ GitHub API.
                </p>
              </div>
              <Link
                to="/activity"
                style={{
                  textDecoration: 'none',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '8px 16px',
                  borderRadius: 8,
                  background: '#16a34a',
                  color: '#ffffff',
                  fontWeight: 600,
                }}
              >
                Mở trang phân tích hoạt động →
              </Link>
            </div>
          </section>

          <section className="card" style={{ marginBottom: '1.5rem', background: '#eff6ff', borderColor: '#bfdbfe' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
              <div>
                <h2 style={{ fontSize: '1.15rem', margin: '0 0 4px', color: '#1e40af' }}>
                  🔍 Phân tích mã nguồn, ngôn ngữ & kiến trúc (PBI-012)
                </h2>
                <p style={{ margin: 0, fontSize: '0.9rem', color: '#1d4ed8' }}>
                  Phân tích cây thư mục repository, phát hiện ngôn ngữ, framework công nghệ và kiến trúc phần mềm.
                </p>
              </div>
              <Link
                to="/analysis"
                style={{
                  textDecoration: 'none',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '8px 16px',
                  borderRadius: 8,
                  background: '#2563eb',
                  color: '#ffffff',
                  fontWeight: 600,
                }}
              >
                Mở trang phân tích mã nguồn →
              </Link>
            </div>
          </section>
        </>
      )}

      <GitHubRepositoriesSection isAuthenticated={Boolean(user)} />

      <section className="card" aria-labelledby="status-heading">
        <h2 id="status-heading">Trạng thái hệ thống</h2>

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
      </section>
    </main>
  )
}
