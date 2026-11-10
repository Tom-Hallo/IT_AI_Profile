import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { env } from '@/shared/config/env'
import { ApiError, apiFetch, isAbortError } from '@/shared/api/client'
import { useAuth } from '@/features/auth/useAuth'
import { fetchRepositories } from './api'
import type { Repository } from './types'

type Mode = 'preset' | 'month' | 'year' | 'custom'
type Scope = 'personal' | 'repository'

interface CommitEvidence {
  sha: string
  html_url: string
  message: string
  committed_at: string
  additions: number
  deletions: number
  verified_authorship: boolean
  is_merge: boolean
  is_bot: boolean
  author_login: string
}

interface PullRequestEvidence {
  number: number
  title: string
  html_url: string
  created_at: string
  state: string
  merged: boolean
  is_personal: boolean
}

interface Analysis {
  repository_id: number
  scope: Scope
  period: { start_utc: string; end_exclusive_utc: string }
  developer: {
    user_id: number
    github_user_id: string | null
    github_login: string | null
  }
  activity: {
    commits: number
    pull_requests_created: number
    additions: number
    deletions: number
  }
  personal_contribution: {
    commits: number
    pull_requests_created: number
    additions: number
    deletions: number
    merge_commits: number
    unverified_commits: number
    bot_commits: number
  }
  repository_context: {
    total_commits: number
    total_pull_requests_created: number
    total_additions: number
    total_deletions: number
    team_commits: number
  }
  evidence: {
    commits: CommitEvidence[]
    pull_requests: PullRequestEvidence[]
  }
  base_code: {
    status: string
    lines: number | null
    as_of_utc: string | null
  }
  sync: {
    last_synced_at: string
    complete_through_end: boolean
  }
  source: string
  data_completeness: {
    status: string
    pr_event_type: string
    scope: string
    confidence: string
  }
  limitations: string[]
}

export function ActivityAnalysisPage() {
  const { repositoryId: routeRepoId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const { user, isLoading: authLoading } = useAuth()

  // Track manual selection fallback when no repo is on URL
  const [manualRepoId, setManualRepoId] = useState('')
  const effectiveRepoId = routeRepoId || searchParams.get('repository_id') || manualRepoId

  // Repositories for dropdown selector
  const [repos, setRepos] = useState<Repository[]>([])
  const [reposLoading, setReposLoading] = useState(false)

  // Derived current repository
  const currentRepo = repos.find((r) => String(r.id) === effectiveRepoId) ?? null

  // Scope state
  const [scope, setScope] = useState<Scope>('personal')

  // Filter state
  const [mode, setMode] = useState<Mode>('preset')
  const [preset, setPreset] = useState('1m')
  const [month, setMonth] = useState('')
  const [year, setYear] = useState('2026')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [timezone, setTimezone] = useState('Asia/Ho_Chi_Minh')

  // UI state for showing evidence
  const [showEvidence, setShowEvidence] = useState(false)

  // Analysis result & error state
  const [data, setData] = useState<Analysis | null>(null)
  const [error, setError] = useState('')
  const [errorCode, setErrorCode] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Abort ongoing request on component unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort()
    }
  }, [])

  // Load available repositories when authenticated
  useEffect(() => {
    if (!user) return

    let cancelled = false

    fetchRepositories({ per_page: 100 })
      .then((res) => {
        if (!cancelled) {
          setRepos(res.items)
        }
      })
      .catch(() => {
        // Soft error for repo list
      })
      .finally(() => {
        if (!cancelled) {
          setReposLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [user])

  // Handle repository change from dropdown
  const handleRepoSelect = (repoId: string) => {
    setManualRepoId(repoId)
    setError('')
    setData(null)

    if (repoId) {
      setSearchParams({ repository_id: repoId }, { replace: true })
    } else {
      setSearchParams({}, { replace: true })
    }
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError('')
    setErrorCode(null)
    setData(null)

    const repoId = effectiveRepoId.trim()
    if (!repoId || !/^\d+$/.test(repoId)) {
      setError('Vui lòng chọn một repository hợp lệ để phân tích.')
      return
    }

    const query = new URLSearchParams({ mode, timezone, scope })
    if (mode === 'preset') query.set('preset', preset)
    if (mode === 'month') {
      if (!month) {
        setError('Vui lòng chọn tháng.')
        return
      }
      query.set('month', month)
    }
    if (mode === 'year') {
      if (!year) {
        setError('Vui lòng nhập năm.')
        return
      }
      query.set('year', year)
    }
    if (mode === 'custom') {
      if (!start || !end) {
        setError('Vui lòng chọn đầy đủ ngày bắt đầu và ngày kết thúc.')
        return
      }
      if (start > end) {
        setError('Ngày bắt đầu không được lớn hơn ngày kết thúc.')
        return
      }
      query.set('start_date', start)
      query.set('end_date', end)
    }

    // Cancel previous request if still running
    abortControllerRef.current?.abort()
    const abortController = new AbortController()
    abortControllerRef.current = abortController

    setLoading(true)
    try {
      const result = await apiFetch<Analysis>(
        `/repositories/${repoId}/activity/analysis?${query.toString()}`,
        {
          signal: abortController.signal,
          timeoutMs: 60000,
        }
      )
      setData(result)
    } catch (err) {
      if (isAbortError(err)) {
        return
      }

      if (err instanceof ApiError && err.kind === 'timeout') {
        setError(
          'Quá thời gian chờ phản hồi từ máy chủ (timeout). Vui lòng thử lại hoặc chọn khoảng thời gian ngắn hơn.'
        )
        setErrorCode(504)
        return
      }

      const status = err instanceof ApiError ? err.status : undefined
      setErrorCode(status ?? null)

      const backendDetail =
        err instanceof ApiError &&
        typeof (err.body as { detail?: string })?.detail === 'string'
          ? (err.body as { detail: string }).detail
          : undefined

      const messages: Record<number, string> = {
        401: 'Phiên đăng nhập đã hết hạn hoặc bạn chưa liên kết GitHub.',
        403: "Repository riêng tư yêu cầu quyền OAuth 'repo'. Vui lòng cấp quyền Private.",
        404: 'Không tìm thấy repository hoặc bạn không có quyền truy cập.',
        409: "Repository chưa hoàn tất đồng bộ. Hãy nhấn 'Đồng bộ ngay' trên Dashboard trước khi phân tích.",
        413: 'Khoảng thời gian chứa quá nhiều dữ liệu (>1000 commits). Vui lòng chọn khoảng thời gian ngắn hơn.',
        422: 'Tham số thời gian hoặc múi giờ không hợp lệ.',
        429: 'GitHub API đang giới hạn tần suất truy vấn (Rate limit). Vui lòng thử lại sau vài phút.',
        500: 'Backend gặp lỗi nội bộ trong quá trình phân tích.',
        502: 'Không thể kết nối hoặc nhận phản hồi từ GitHub API.',
      }
      setError(backendDetail || messages[status ?? 0] || 'Không thể tải dữ liệu phân tích hoạt động.')
    } finally {
      if (abortControllerRef.current === abortController) {
        setLoading(false)
      }
    }
  }

  const handleGitHubLogin = () => {
    if (!env.apiBaseUrl) return
    window.location.assign(`${env.apiBaseUrl}/auth/github`)
  }

  const handleGrantPrivate = () => {
    if (!env.apiBaseUrl) return
    window.location.assign(`${env.apiBaseUrl}/auth/github?include_private=true`)
  }

  return (
    <main style={{ maxWidth: 960, margin: '2rem auto', padding: '1.5rem', fontFamily: 'inherit' }}>
      <header style={{ marginBottom: '1.5rem' }}>
        <Link
          to="/"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            marginBottom: '1rem',
            color: 'var(--color-primary, #6366f1)',
            textDecoration: 'none',
            fontWeight: 500,
          }}
        >
          ← Quay lại Dashboard
        </Link>
        <span
          style={{
            display: 'block',
            fontSize: '0.75rem',
            fontWeight: 700,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            color: 'var(--color-text-muted, #64748b)',
          }}
        >
          PBI-010 · IT TALENT AI PROFILE
        </span>
        <h1 style={{ fontSize: '1.875rem', margin: '0.25rem 0 0.5rem', fontWeight: 700 }}>
          GitHub Activity Analysis
        </h1>
        <p style={{ color: 'var(--color-text-muted, #64748b)', margin: 0 }}>
          Phân tích đóng góp lập trình viên theo thời gian thực tế từ GitHub API, tách biệt đóng góp cá nhân xác thực với bối cảnh dự án.
        </p>
      </header>

      {/* Authentication Guard */}
      {!authLoading && !user && (
        <section
          style={{
            padding: '1.5rem',
            background: 'var(--color-surface, #ffffff)',
            borderRadius: 12,
            border: '1px solid var(--color-border, #e2e8f0)',
            marginBottom: '1.5rem',
            textAlign: 'center',
          }}
        >
          <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>Yêu cầu đăng nhập GitHub</h2>
          <p style={{ color: 'var(--color-text-muted, #64748b)', marginBottom: '1rem' }}>
            Bạn cần đăng nhập bằng GitHub để truy cập danh sách repository đã đồng bộ và thực hiện phân tích hoạt động.
          </p>
          <button
            type="button"
            className="button"
            onClick={handleGitHubLogin}
            style={{
              padding: '0.625rem 1.25rem',
              background: '#24292f',
              color: '#ffffff',
              borderRadius: 8,
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Đăng nhập bằng GitHub
          </button>
        </section>
      )}

      {/* Repository Selector Dropdown */}
      <section
        style={{
          background: 'var(--color-surface, #ffffff)',
          padding: '1.25rem',
          borderRadius: 12,
          border: '1px solid var(--color-border, #e2e8f0)',
          marginBottom: '1.5rem',
        }}
      >
        <label
          htmlFor="repo-picker"
          style={{ display: 'block', fontWeight: 600, marginBottom: '0.5rem' }}
        >
          Chọn Repository phân tích:
        </label>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <select
            id="repo-picker"
            value={effectiveRepoId}
            onChange={(e) => handleRepoSelect(e.target.value)}
            disabled={reposLoading || loading}
            style={{
              flex: 1,
              minWidth: 280,
              padding: '0.625rem 0.875rem',
              borderRadius: 8,
              border: '1px solid var(--color-border, #cbd5e1)',
              background: 'var(--color-bg, #ffffff)',
              fontSize: '0.95rem',
            }}
          >
            <option value="">-- Chọn repository trong danh sách đã đồng bộ --</option>
            {repos.map((repo) => (
              <option key={repo.id} value={String(repo.id)}>
                {repo.full_name} ({repo.private ? 'Private' : 'Public'}) — #{repo.id}
              </option>
            ))}
          </select>

          {reposLoading && (
            <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted, #64748b)' }}>
              Đang tải danh sách...
            </span>
          )}

          {repos.length === 0 && !reposLoading && user && (
            <span style={{ fontSize: '0.85rem', color: '#dc2626' }}>
              Chưa có repository nào. Hãy nhấn &quot;Đồng bộ ngay&quot; tại Dashboard.
            </span>
          )}
        </div>

        {currentRepo && (
          <div
            style={{
              marginTop: '0.875rem',
              padding: '0.625rem 0.875rem',
              background: 'var(--color-surface-subtle, #f8fafc)',
              borderRadius: 8,
              fontSize: '0.85rem',
              display: 'flex',
              gap: 16,
              alignItems: 'center',
            }}
          >
            <span>
              <strong>Tên:</strong> {currentRepo.name}
            </span>
            <span>
              <strong>Nhánh mặc định:</strong> {currentRepo.default_branch}
            </span>
            <span>
              <strong>Phạm vi:</strong>{' '}
              {currentRepo.private ? '🔒 Private' : '◉ Public'}
            </span>
            <a
              href={currentRepo.html_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ marginLeft: 'auto', color: 'var(--color-primary, #6366f1)' }}
            >
              Mở trên GitHub ↗
            </a>
          </div>
        )}
      </section>

      {/* Filter and Analyze Form */}
      <section
        style={{
          background: 'var(--color-surface, #ffffff)',
          padding: '1.5rem',
          borderRadius: 12,
          border: '1px solid var(--color-border, #e2e8f0)',
          marginBottom: '1.5rem',
        }}
      >
        <form onSubmit={(e) => void submit(e)} style={{ display: 'grid', gap: '1.25rem' }}>
          {/* Scope Selector: Personal vs Repository */}
          <div>
            <label style={{ display: 'block', fontWeight: 600, marginBottom: '0.5rem' }}>
              Phạm vi phân tích (Analysis Scope):
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '0.75rem' }}>
              <label
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                  padding: '0.875rem',
                  borderRadius: 8,
                  border: `2px solid ${scope === 'personal' ? 'var(--color-primary, #6366f1)' : '#e2e8f0'}`,
                  background: scope === 'personal' ? '#f5f3ff' : '#ffffff',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="radio"
                  name="scope"
                  value="personal"
                  checked={scope === 'personal'}
                  onChange={() => setScope('personal')}
                  style={{ marginTop: 3 }}
                />
                <div>
                  <strong style={{ display: 'block', fontSize: '0.95rem', color: '#1e1b4b' }}>
                    Đóng góp cá nhân (Personal Contribution)
                  </strong>
                  <span style={{ fontSize: '0.8rem', color: '#64748b', lineHeight: 1.4, display: 'block', marginTop: 2 }}>
                    Chỉ tính các commit và Pull Request đã xác thực thuộc về tài khoản GitHub của bạn. Loại bỏ bot và đóng góp của đồng đội.
                  </span>
                </div>
              </label>

              <label
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                  padding: '0.875rem',
                  borderRadius: 8,
                  border: `2px solid ${scope === 'repository' ? 'var(--color-primary, #6366f1)' : '#e2e8f0'}`,
                  background: scope === 'repository' ? '#f8fafc' : '#ffffff',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="radio"
                  name="scope"
                  value="repository"
                  checked={scope === 'repository'}
                  onChange={() => setScope('repository')}
                  style={{ marginTop: 3 }}
                />
                <div>
                  <strong style={{ display: 'block', fontSize: '0.95rem', color: '#0f172a' }}>
                    Toàn bộ Repository (Repository Activity)
                  </strong>
                  <span style={{ fontSize: '0.8rem', color: '#64748b', lineHeight: 1.4, display: 'block', marginTop: 2 }}>
                    Bao gồm hoạt động của tất cả thành viên trong repository làm bối cảnh dự án (project context).
                  </span>
                </div>
              </label>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontWeight: 500 }}>
              Chế độ thời gian:
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as Mode)}
                style={{ padding: '0.5rem 0.75rem', borderRadius: 8, border: '1px solid #cbd5e1' }}
              >
                <option value="preset">Khoảng gần đây (Presets)</option>
                <option value="month">Theo tháng</option>
                <option value="year">Theo năm</option>
                <option value="custom">Khoảng tùy chọn</option>
              </select>
            </label>

            {mode === 'preset' && (
              <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontWeight: 500 }}>
                Khoảng thời gian:
                <select
                  value={preset}
                  onChange={(e) => setPreset(e.target.value)}
                  style={{ padding: '0.5rem 0.75rem', borderRadius: 8, border: '1px solid #cbd5e1' }}
                >
                  <option value="1m">1 tháng gần nhất</option>
                  <option value="3m">3 tháng gần nhất</option>
                  <option value="6m">6 tháng gần nhất</option>
                  <option value="1y">1 năm gần nhất</option>
                  <option value="all">Toàn bộ lịch sử (all)</option>
                </select>
              </label>
            )}

            {mode === 'month' && (
              <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontWeight: 500 }}>
                Chọn tháng:
                <input
                  type="month"
                  required
                  value={month}
                  onChange={(e) => setMonth(e.target.value)}
                  style={{ padding: '0.5rem 0.75rem', borderRadius: 8, border: '1px solid #cbd5e1' }}
                />
              </label>
            )}

            {mode === 'year' && (
              <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontWeight: 500 }}>
                Nhập năm:
                <input
                  type="number"
                  required
                  min="2000"
                  max="2100"
                  value={year}
                  onChange={(e) => setYear(e.target.value)}
                  style={{ padding: '0.5rem 0.75rem', borderRadius: 8, border: '1px solid #cbd5e1' }}
                />
              </label>
            )}

            {mode === 'custom' && (
              <>
                <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontWeight: 500 }}>
                  Từ ngày:
                  <input
                    type="date"
                    required
                    value={start}
                    onChange={(e) => setStart(e.target.value)}
                    style={{ padding: '0.5rem 0.75rem', borderRadius: 8, border: '1px solid #cbd5e1' }}
                  />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontWeight: 500 }}>
                  Đến ngày:
                  <input
                    type="date"
                    required
                    min={start}
                    value={end}
                    onChange={(e) => setEnd(e.target.value)}
                    style={{ padding: '0.5rem 0.75rem', borderRadius: 8, border: '1px solid #cbd5e1' }}
                  />
                </label>
              </>
            )}

            <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontWeight: 500 }}>
              Múi giờ phân tích:
              <select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                style={{ padding: '0.5rem 0.75rem', borderRadius: 8, border: '1px solid #cbd5e1' }}
              >
                <option value="Asia/Ho_Chi_Minh">Việt Nam (UTC+7)</option>
                <option value="UTC">UTC (Chuẩn quốc tế)</option>
                <option value="America/New_York">New York (UTC-5)</option>
                <option value="Europe/London">London (UTC+0)</option>
                <option value="Asia/Tokyo">Tokyo (UTC+9)</option>
              </select>
            </label>
          </div>

          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: '0.5rem' }}>
            <button
              type="submit"
              disabled={loading || !effectiveRepoId}
              style={{
                padding: '0.625rem 1.5rem',
                borderRadius: 8,
                background: 'var(--color-primary, #6366f1)',
                color: '#ffffff',
                border: 'none',
                fontWeight: 600,
                cursor: loading || !effectiveRepoId ? 'not-allowed' : 'pointer',
                opacity: loading || !effectiveRepoId ? 0.6 : 1,
              }}
            >
              {loading ? 'Đang phân tích...' : 'Phân tích hoạt động'}
            </button>

            {!effectiveRepoId && (
              <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted, #64748b)' }}>
                Hãy chọn một repository ở phía trên để tiếp tục.
              </span>
            )}
          </div>
        </form>

        {/* Error Alert Box */}
        {error && (
          <div
            role="alert"
            style={{
              marginTop: '1.25rem',
              padding: '1rem',
              borderRadius: 8,
              background: '#fef2f2',
              border: '1px solid #fecaca',
              color: '#991b1b',
            }}
          >
            <p style={{ margin: 0, fontWeight: 500 }}>{error}</p>
            {errorCode === 403 && (
              <button
                type="button"
                onClick={handleGrantPrivate}
                style={{
                  marginTop: '0.75rem',
                  padding: '0.5rem 1rem',
                  background: '#991b1b',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontWeight: 600,
                }}
              >
                Cấp quyền GitHub Private ngay →
              </button>
            )}
          </div>
        )}
      </section>

      {/* Analysis Results Display */}
      {data && (
        <section
          aria-live="polite"
          style={{
            background: 'var(--color-surface, #ffffff)',
            padding: '1.5rem',
            borderRadius: 12,
            border: '1px solid var(--color-border, #e2e8f0)',
          }}
        >
          {/* Header & Badges */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12, marginBottom: '1rem' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <h2 style={{ fontSize: '1.35rem', margin: 0, fontWeight: 700 }}>
                  Kết quả phân tích hoạt động
                </h2>
                <span
                  style={{
                    fontSize: '0.8rem',
                    padding: '2px 8px',
                    borderRadius: 6,
                    fontWeight: 600,
                    background: data.scope === 'personal' ? '#e0e7ff' : '#f1f5f9',
                    color: data.scope === 'personal' ? '#4338ca' : '#475569',
                  }}
                >
                  {data.scope === 'personal' ? '👤 Đóng góp cá nhân' : '📁 Toàn bộ Repository'}
                </span>
              </div>
              <p style={{ color: 'var(--color-text-muted, #64748b)', fontSize: '0.85rem', margin: 0 }}>
                Lập trình viên: <strong>{data.developer.github_login ? `@${data.developer.github_login}` : `User #${data.developer.user_id}`}</strong> · Khoảng UTC: <code>{data.period.start_utc}</code> → <code>{data.period.end_exclusive_utc}</code>
              </p>
            </div>

            <span
              style={{
                fontSize: '0.8rem',
                padding: '4px 8px',
                borderRadius: 6,
                background: '#ecfdf5',
                color: '#065f46',
                fontWeight: 600,
              }}
            >
              Nguồn: {data.source}
            </span>
          </div>

          {/* Context Comparison Banner */}
          <div
            style={{
              padding: '0.875rem 1rem',
              borderRadius: 8,
              background: data.scope === 'personal' ? '#f5f3ff' : '#f8fafc',
              border: `1px solid ${data.scope === 'personal' ? '#ddd6fe' : '#e2e8f0'}`,
              marginBottom: '1.25rem',
              fontSize: '0.9rem',
              color: '#334155',
            }}
          >
            {data.scope === 'personal' ? (
              <span>
                📊 <strong>Bối cảnh dự án:</strong> Bạn đã đóng góp <strong>{data.personal_contribution.commits}</strong> / <strong>{data.repository_context.total_commits}</strong> commits của repository
                {data.repository_context.total_commits > 0
                  ? ` (${Math.round((data.personal_contribution.commits / data.repository_context.total_commits) * 100)}%)`
                  : ''}
                , tạo <strong>{data.personal_contribution.pull_requests_created}</strong> / <strong>{data.repository_context.total_pull_requests_created}</strong> PRs. Đồng đội đã đóng góp <strong>{data.repository_context.team_commits}</strong> commits.
                {data.personal_contribution.merge_commits > 0 && ` (${data.personal_contribution.merge_commits} merge commits)`}
              </span>
            ) : (
              <span>
                📁 <strong>Toàn bộ dự án:</strong> Tổng số <strong>{data.repository_context.total_commits}</strong> commits (+{data.repository_context.total_additions} / -{data.repository_context.total_deletions}), <strong>{data.repository_context.total_pull_requests_created}</strong> PRs. Trong đó bạn đóng góp <strong>{data.personal_contribution.commits}</strong> commits cá nhân.
              </span>
            )}
          </div>

          {/* Metrics Grid */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: '1rem',
              marginBottom: '1.5rem',
            }}
          >
            <div style={{ padding: '1rem', borderRadius: 8, background: '#f8fafc', border: '1px solid #e2e8f0' }}>
              <span style={{ fontSize: '0.8rem', color: '#64748b', textTransform: 'uppercase' }}>
                {data.scope === 'personal' ? 'Commits cá nhân' : 'Tổng Commits Repo'}
              </span>
              <strong style={{ display: 'block', fontSize: '1.75rem', marginTop: 4, color: '#0f172a' }}>
                {data.activity.commits}
              </strong>
              {data.scope === 'personal' && (
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                  trên tổng số {data.repository_context.total_commits} repo
                </span>
              )}
            </div>

            <div style={{ padding: '1rem', borderRadius: 8, background: '#f8fafc', border: '1px solid #e2e8f0' }}>
              <span style={{ fontSize: '0.8rem', color: '#64748b', textTransform: 'uppercase' }}>
                {data.scope === 'personal' ? 'PRs cá nhân tạo' : 'Tổng PRs tạo'}
              </span>
              <strong style={{ display: 'block', fontSize: '1.75rem', marginTop: 4, color: '#0f172a' }}>
                {data.activity.pull_requests_created}
              </strong>
              {data.scope === 'personal' && (
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                  trên tổng số {data.repository_context.total_pull_requests_created} repo
                </span>
              )}
            </div>

            <div style={{ padding: '1rem', borderRadius: 8, background: '#f8fafc', border: '1px solid #e2e8f0' }}>
              <span style={{ fontSize: '0.8rem', color: '#64748b', textTransform: 'uppercase' }}>Dòng thêm / xóa</span>
              <strong style={{ display: 'block', fontSize: '1.35rem', marginTop: 8, color: '#0f172a' }}>
                <span style={{ color: '#16a34a' }}>+{data.activity.additions}</span> / <span style={{ color: '#dc2626' }}>-{data.activity.deletions}</span>
              </strong>
            </div>

            <div style={{ padding: '1rem', borderRadius: 8, background: '#f8fafc', border: '1px solid #e2e8f0' }}>
              <span style={{ fontSize: '0.8rem', color: '#64748b', textTransform: 'uppercase' }}>Code nền trước kỳ</span>
              <strong style={{ display: 'block', fontSize: '1.25rem', marginTop: 8, color: '#0f172a' }}>
                {data.base_code.status === 'available' && data.base_code.lines !== null
                  ? `${data.base_code.lines.toLocaleString()} LOC`
                  : 'Chưa có snapshot'}
              </strong>
            </div>
          </div>

          {/* Sync warning */}
          {!data.sync.complete_through_end && (
            <div
              style={{
                padding: '0.75rem 1rem',
                borderRadius: 8,
                background: '#fffbeb',
                border: '1px solid #fef3c7',
                color: '#92400e',
                fontSize: '0.85rem',
                marginBottom: '1rem',
              }}
            >
              ⚠️ <strong>Lưu ý đồng bộ:</strong> Dữ liệu metadata đồng bộ có thể chưa bao phủ toàn bộ kỳ truy vấn (lần đồng bộ cuối: {new Date(data.sync.last_synced_at).toLocaleString('vi-VN')}).
            </div>
          )}

          {/* Evidence Toggle Button */}
          <div style={{ marginBottom: '1.5rem' }}>
            <button
              type="button"
              onClick={() => setShowEvidence((prev) => !prev)}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: 6,
                background: showEvidence ? '#e2e8f0' : '#f1f5f9',
                color: '#334155',
                border: '1px solid #cbd5e1',
                fontSize: '0.85rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {showEvidence ? '▲ Ẩn chi tiết bằng chứng (Evidence)' : '▼ Xem chi tiết bằng chứng (Evidence commits & PRs)'}
            </button>
          </div>

          {/* Evidence Details Section */}
          {showEvidence && (
            <div style={{ marginBottom: '1.5rem', padding: '1rem', borderRadius: 8, background: '#f8fafc', border: '1px solid #e2e8f0' }}>
              <h3 style={{ fontSize: '1.05rem', margin: '0 0 0.75rem', fontWeight: 600 }}>
                Bằng chứng hoạt động ({data.evidence.commits.length} commits, {data.evidence.pull_requests.length} PRs)
              </h3>

              {/* Commits Evidence List */}
              <div style={{ marginBottom: '1rem' }}>
                <h4 style={{ fontSize: '0.9rem', color: '#475569', marginBottom: '0.5rem' }}>Danh sách Commits:</h4>
                {data.evidence.commits.length === 0 ? (
                  <p style={{ fontSize: '0.85rem', color: '#64748b', fontStyle: 'italic' }}>Không có commit nào trong kỳ đã chọn.</p>
                ) : (
                  <div style={{ maxHeight: 260, overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: 6, background: '#fff' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                      <thead>
                        <tr style={{ background: '#f1f5f9', borderBottom: '1px solid #cbd5e1', textAlign: 'left' }}>
                          <th style={{ padding: '6px 10px' }}>SHA</th>
                          <th style={{ padding: '6px 10px' }}>Thông điệp</th>
                          <th style={{ padding: '6px 10px' }}>Thời gian</th>
                          <th style={{ padding: '6px 10px' }}>Thay đổi</th>
                          <th style={{ padding: '6px 10px' }}>Thuộc tính</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.evidence.commits.map((c) => (
                          <tr key={c.sha} style={{ borderBottom: '1px solid #f1f5f9' }}>
                            <td style={{ padding: '6px 10px', fontFamily: 'monospace' }}>
                              <a href={c.html_url} target="_blank" rel="noopener noreferrer" style={{ color: '#4f46e5' }}>
                                {c.sha.slice(0, 7)}
                              </a>
                            </td>
                            <td style={{ padding: '6px 10px', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.message}>
                              {c.message}
                            </td>
                            <td style={{ padding: '6px 10px', color: '#64748b' }}>
                              {new Date(c.committed_at).toLocaleDateString('vi-VN')}
                            </td>
                            <td style={{ padding: '6px 10px' }}>
                              <span style={{ color: '#16a34a' }}>+{c.additions}</span> / <span style={{ color: '#dc2626' }}>-{c.deletions}</span>
                            </td>
                            <td style={{ padding: '6px 10px' }}>
                              {c.verified_authorship && (
                                <span style={{ padding: '2px 6px', borderRadius: 4, background: '#dcfce7', color: '#15803d', fontSize: '0.75rem', marginRight: 4 }}>
                                  ✓ Verified
                                </span>
                              )}
                              {c.is_merge && (
                                <span style={{ padding: '2px 6px', borderRadius: 4, background: '#fef3c7', color: '#b45309', fontSize: '0.75rem', marginRight: 4 }}>
                                  Merge
                                </span>
                              )}
                              {c.is_bot && (
                                <span style={{ padding: '2px 6px', borderRadius: 4, background: '#fee2e2', color: '#b91c1c', fontSize: '0.75rem' }}>
                                  Bot
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* PRs Evidence List */}
              <div>
                <h4 style={{ fontSize: '0.9rem', color: '#475569', marginBottom: '0.5rem' }}>Danh sách Pull Requests:</h4>
                {data.evidence.pull_requests.length === 0 ? (
                  <p style={{ fontSize: '0.85rem', color: '#64748b', fontStyle: 'italic' }}>Không có pull request nào được tạo trong kỳ đã chọn.</p>
                ) : (
                  <div style={{ maxHeight: 200, overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: 6, background: '#fff' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                      <thead>
                        <tr style={{ background: '#f1f5f9', borderBottom: '1px solid #cbd5e1', textAlign: 'left' }}>
                          <th style={{ padding: '6px 10px' }}>#</th>
                          <th style={{ padding: '6px 10px' }}>Tiêu đề</th>
                          <th style={{ padding: '6px 10px' }}>Trạng thái</th>
                          <th style={{ padding: '6px 10px' }}>Ngày tạo</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.evidence.pull_requests.map((pr) => (
                          <tr key={pr.number} style={{ borderBottom: '1px solid #f1f5f9' }}>
                            <td style={{ padding: '6px 10px' }}>
                              <a href={pr.html_url} target="_blank" rel="noopener noreferrer" style={{ color: '#4f46e5', fontWeight: 600 }}>
                                #{pr.number}
                              </a>
                            </td>
                            <td style={{ padding: '6px 10px' }}>{pr.title}</td>
                            <td style={{ padding: '6px 10px' }}>
                              <span
                                style={{
                                  padding: '2px 6px',
                                  borderRadius: 4,
                                  fontSize: '0.75rem',
                                  background: pr.merged ? '#ede9fe' : pr.state === 'open' ? '#dcfce7' : '#fee2e2',
                                  color: pr.merged ? '#6d28d9' : pr.state === 'open' ? '#15803d' : '#b91c1c',
                                }}
                              >
                                {pr.merged ? 'Merged' : pr.state}
                              </span>
                            </td>
                            <td style={{ padding: '6px 10px', color: '#64748b' }}>
                              {new Date(pr.created_at).toLocaleDateString('vi-VN')}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Trustworthy Downstream & Guardrails Section */}
          <div
            style={{
              padding: '1rem',
              borderRadius: 8,
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              marginBottom: '1rem',
              fontSize: '0.85rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: '0.5rem' }}>
              <span style={{ fontWeight: 600, color: '#0f172a' }}>Tính toàn vẹn dữ liệu (Data Integrity):</span>
              <span style={{ padding: '2px 6px', borderRadius: 4, background: '#dcfce7', color: '#15803d', fontSize: '0.75rem', fontWeight: 600 }}>
                PR Event: {data.data_completeness.pr_event_type}
              </span>
              <span style={{ padding: '2px 6px', borderRadius: 4, background: '#e0e7ff', color: '#4338ca', fontSize: '0.75rem', fontWeight: 600 }}>
                Độ tin cậy: {data.data_completeness.confidence}
              </span>
            </div>
            <p style={{ margin: 0, color: '#64748b', lineHeight: 1.5 }}>
              🛡️ <strong>Nguyên tắc đánh giá:</strong> Số lượng commit và dòng thay đổi chỉ phản ánh tần suất hoạt động thô theo thời gian. Hệ thống <strong>không</strong> tự động quy đổi khối lượng này thành điểm kỹ năng (AI Skill Score) để bảo đảm tính khách quan và tránh sai lệch.
            </p>
          </div>

          {/* Limitations List */}
          {data.limitations.length > 0 && (
            <div>
              <h3 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.5rem' }}>Giới hạn & Lưu ý:</h3>
              <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.85rem', color: '#64748b' }}>
                {data.limitations.map((item) => (
                  <li key={item} style={{ marginBottom: 4 }}>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </main>
  )
}
