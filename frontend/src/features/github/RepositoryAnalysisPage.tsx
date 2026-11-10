import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { ApiError, isAbortError } from '@/shared/api/client'
import { useAuth } from '@/features/auth/useAuth'
import {
  cancelAnalysisJob,
  createAnalysisJob,
  fetchAnalysisEvidence,
  fetchAnalysisJob,
  fetchLatestAnalysis,
  fetchRepositories,
  retryAnalysisJob,
  triggerRepositoryAnalysis,
} from './api'
import type {
  AnalysisJobInfo,
  EvidenceItem,
  Repository,
  RepositoryAnalysisResult,
} from './types'

export function RepositoryAnalysisPage() {
  const { repositoryId: routeRepoId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const { user } = useAuth()

  // Track selected repository
  const [manualRepoId, setManualRepoId] = useState('')
  const effectiveRepoId = routeRepoId || searchParams.get('repository_id') || manualRepoId

  // Repositories for dropdown selector
  const [repos, setRepos] = useState<Repository[]>([])
  const [reposLoading, setReposLoading] = useState(false)

  // Options
  const [scope, setScope] = useState<'all' | 'public' | 'private'>('all')
  const [useBackgroundJob, setUseBackgroundJob] = useState(false)

  // Optional time range (PBI-010 integration)
  const [enableTimeRange, setEnableTimeRange] = useState(false)
  const [mode, setMode] = useState<'preset' | 'month' | 'year' | 'custom'>('preset')
  const [preset, setPreset] = useState('3m')
  const [month, setMonth] = useState('')
  const [year, setYear] = useState(String(new Date().getFullYear()))
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [timezone, setTimezone] = useState('Asia/Ho_Chi_Minh')

  // Analysis state
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [errorCode, setErrorCode] = useState<number | null>(null)
  const [data, setData] = useState<RepositoryAnalysisResult | null>(null)
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([])
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [evidenceFilter, setEvidenceFilter] = useState<string>('all')

  // Background Job tracking
  const [activeJob, setActiveJob] = useState<AnalysisJobInfo | null>(null)
  const [jobActionBusy, setJobActionBusy] = useState(false)

  const abortControllerRef = useRef<AbortController | null>(null)

  const loadEvidence = async (repoId: number, commitSha?: string) => {
    setEvidenceLoading(true)
    try {
      const evRes = await fetchAnalysisEvidence(repoId, commitSha)
      setEvidenceList(evRes.items)
    } catch (err) {
      console.warn('Could not load detailed evidence list', err)
    } finally {
      setEvidenceLoading(false)
    }
  }

  // Load repositories for selector
  useEffect(() => {
    if (!user) return
    let active = true

    fetchRepositories({ per_page: 100 })
      .then((res) => {
        if (!active) return
        setRepos(res.items)
        if (!effectiveRepoId && res.items.length > 0) {
          const first = res.items[0]
          setManualRepoId(String(first.id))
        }
      })
      .catch((err) => {
        if (!active) return
        console.error('Failed to load repositories', err)
      })
      .finally(() => {
        if (active) setReposLoading(false)
      })

    return () => {
      active = false
    }
  }, [user, effectiveRepoId])

  // When repo changes, automatically attempt to fetch latest saved analysis
  useEffect(() => {
    if (!effectiveRepoId) return
    const repoIdNum = Number(effectiveRepoId)
    if (!repoIdNum) return

    let active = true
    fetchLatestAnalysis(repoIdNum)
      .then((res) => {
        if (!active) return
        setData(res)
        setError(null)
        // Also fetch evidence
        void loadEvidence(repoIdNum, res.commit_sha)
      })
      .catch(() => {
        // Not analyzed yet or no saved results - normal for fresh repo
        if (!active) return
        setData(null)
        setEvidenceList([])
      })

    return () => {
      active = false
    }
  }, [effectiveRepoId])

  // Poll active background job
  useEffect(() => {
    if (!activeJob) return
    const isTerminal = ['succeeded', 'failed', 'cancelled'].includes(activeJob.status)
    if (isTerminal) {
      if (activeJob.status === 'succeeded' && effectiveRepoId) {
        // Load completed results from database
        const repoIdNum = Number(effectiveRepoId)
        void fetchLatestAnalysis(repoIdNum).then((res) => {
          setData(res)
          void loadEvidence(repoIdNum, res.commit_sha)
        })
      }
      return
    }

    const timer = setTimeout(() => {
      fetchAnalysisJob(activeJob.id)
        .then((updated) => {
          setActiveJob(updated)
        })
        .catch((err) => {
          console.warn('Failed to poll analysis job', err)
        })
    }, 2000)

    return () => clearTimeout(timer)
  }, [activeJob, effectiveRepoId])

  const handleRepoChange = (newRepoId: string) => {
    setManualRepoId(newRepoId)
    setSearchParams({ repository_id: newRepoId })
    setError(null)
    setData(null)
    setEvidenceList([])
    setActiveJob(null)
  }

  const handleCancelJob = async () => {
    if (!activeJob) return
    setJobActionBusy(true)
    try {
      const res = await cancelAnalysisJob(activeJob.id)
      setActiveJob(res)
    } catch {
      setError('Không thể gửi yêu cầu hủy tiến trình.')
    } finally {
      setJobActionBusy(false)
    }
  }

  const handleRetryJob = async () => {
    if (!activeJob) return
    setJobActionBusy(true)
    try {
      const res = await retryAnalysisJob(activeJob.id)
      setActiveJob(res)
    } catch {
      setError('Không thể thử lại phân tích nền.')
    } finally {
      setJobActionBusy(false)
    }
  }

  const handleAnalyze = async () => {
    setError(null)
    setErrorCode(null)

    if (!effectiveRepoId || !/^\d+$/.test(effectiveRepoId)) {
      setError('Vui lòng chọn một repository hợp lệ để phân tích.')
      return
    }

    const repoId = Number(effectiveRepoId)
    const currentRepo = repos.find((r) => r.id === repoId)

    if (scope === 'public' && currentRepo?.private) {
      setError('Repository là riêng tư (Private), không thể phân tích với phạm vi "Công khai".')
      return
    }
    if (scope === 'private' && currentRepo && !currentRepo.private) {
      setError('Repository là công khai (Public), không thể phân tích với phạm vi "Riêng tư".')
      return
    }

    // Background job mode
    if (useBackgroundJob) {
      setLoading(true)
      try {
        const jobPayload: {
          scope: string
          branch?: string
          mode?: string
          preset?: string
          month?: string
          year?: string
          start_date?: string
          end_date?: string
          timezone?: string
        } = {
          scope: scope === 'all' ? 'full' : scope,
          branch: currentRepo?.default_branch || 'master',
        }

        if (enableTimeRange) {
          jobPayload.mode = mode
          jobPayload.timezone = timezone
          if (mode === 'preset') jobPayload.preset = preset
          if (mode === 'month') jobPayload.month = month
          if (mode === 'year') jobPayload.year = year
          if (mode === 'custom') {
            if (!start || !end) {
              setError('Vui lòng nhập đầy đủ ngày bắt đầu và kết thúc.')
              setLoading(false)
              return
            }
            if (start > end) {
              setError('Ngày bắt đầu không được lớn hơn ngày kết thúc.')
              setLoading(false)
              return
            }
            jobPayload.start_date = start
            jobPayload.end_date = end
          }
        }

        const job = await createAnalysisJob(repoId, jobPayload)
        setActiveJob(job)
      } catch (err) {
        handleApiError(err)
      } finally {
        setLoading(false)
      }
      return
    }

    // Direct synchronous analysis mode
    abortControllerRef.current?.abort()
    const abortController = new AbortController()
    abortControllerRef.current = abortController

    setLoading(true)
    try {
      const payload: {
        scope: 'all' | 'public' | 'private' | 'full'
        branch?: string
        mode?: string
        preset?: string
        month?: string
        year?: string
        start_date?: string
        end_date?: string
        timezone?: string
      } = {
        scope,
        branch: currentRepo?.default_branch || 'master',
      }

      if (enableTimeRange) {
        payload.mode = mode
        payload.timezone = timezone
        if (mode === 'preset') payload.preset = preset
        if (mode === 'month') payload.month = month
        if (mode === 'year') payload.year = year
        if (mode === 'custom') {
          if (!start || !end) {
            setError('Vui lòng nhập đầy đủ ngày bắt đầu và kết thúc.')
            setLoading(false)
            return
          }
          if (start > end) {
            setError('Ngày bắt đầu không được lớn hơn ngày kết thúc.')
            setLoading(false)
            return
          }
          payload.start_date = start
          payload.end_date = end
        }
      }

      const result = await triggerRepositoryAnalysis(repoId, payload, abortController.signal)
      setData(result)
      await loadEvidence(repoId, result.commit_sha)
    } catch (err) {
      if (isAbortError(err)) return
      handleApiError(err)
    } finally {
      setLoading(false)
    }
  }

  const handleApiError = (err: unknown) => {
    if (err instanceof ApiError && err.kind === 'timeout') {
      setError('Quá thời gian chờ phản hồi từ máy chủ (timeout). Vui lòng thử lại với chế độ chạy nền.')
      setErrorCode(504)
      return
    }

    const status = err instanceof ApiError ? err.status : undefined
    setErrorCode(status ?? null)

    let backendDetail: string | undefined
    if (err instanceof ApiError && err.body && typeof err.body === 'object') {
      const bodyObj = err.body as { detail?: unknown; message?: string }
      if (typeof bodyObj.detail === 'string') {
        backendDetail = bodyObj.detail
      } else if (Array.isArray(bodyObj.detail)) {
        const issues = bodyObj.detail.map((item: { loc?: unknown[]; msg?: string }) => {
          const field = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : ''
          return field ? `${field}: ${item.msg}` : item.msg || 'Dữ liệu không hợp lệ'
        })
        backendDetail = `Lỗi tham số (${issues.join('; ')})`
      } else if (typeof bodyObj.message === 'string') {
        backendDetail = bodyObj.message
      }
    }

    const messages: Record<number, string> = {
      401: 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại qua GitHub.',
      403: backendDetail || "Repository riêng tư yêu cầu quyền OAuth 'repo'. Vui lòng cấp quyền Private.",
      404: 'Không tìm thấy repository hoặc bạn không có quyền truy cập.',
      422: backendDetail || 'Tham số yêu cầu phân tích không hợp lệ.',
      429: 'GitHub API đang giới hạn tần suất (Rate limit). Vui lòng thử lại sau vài phút.',
      500: backendDetail || 'Backend gặp sự cố khi đọc cây thư mục repository.',
      503: 'Hàng đợi phân tích (Redis/Worker) tạm thời không khả dụng.',
    }

    setError(messages[status ?? 0] ?? backendDetail ?? 'Không thể thực hiện phân tích.')
  }

  const selectedRepo = repos.find((r) => String(r.id) === effectiveRepoId)

  const filteredEvidence = evidenceList.filter((e) => {
    if (evidenceFilter === 'all') return true
    return e.finding_type === evidenceFilter
  })

  return (
    <main style={{ maxWidth: 1140, margin: '2rem auto', padding: '0 1.5rem', fontFamily: 'inherit' }}>
      {/* Navigation breadcrumbs */}
      <nav style={{ marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.9rem' }}>
        <Link to="/" style={{ color: 'var(--color-primary, #2563eb)', textDecoration: 'none', fontWeight: 500 }}>
          ← Quay lại Dashboard
        </Link>
        {effectiveRepoId && (
          <>
            <span style={{ color: 'var(--color-text-muted, #94a3b8)' }}>/</span>
            <Link
              to={`/repositories/${effectiveRepoId}/activity`}
              style={{ color: 'var(--color-text-muted, #64748b)', textDecoration: 'none' }}
            >
              📊 Phân tích hoạt động (PBI-010)
            </Link>
          </>
        )}
      </nav>

      {/* Header */}
      <header style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
          <span style={{ fontSize: '1.5rem' }}>🔍</span>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--color-text, #0f172a)' }}>
            Phân tích mã nguồn, ngôn ngữ & kiến trúc
          </h1>
        </div>
        <p style={{ margin: 0, color: 'var(--color-text-muted, #64748b)', fontSize: '0.95rem' }}>
          PBI-012: Phân tích cây thư mục, nhận diện ngôn ngữ, framework công nghệ và cấu trúc kiến trúc từ dẫn chứng thực tế.
        </p>
      </header>

      {/* Configuration & Selection Card */}
      <section className="card" style={{ marginBottom: '2rem', padding: '1.5rem', background: 'var(--color-surface, #ffffff)' }}>
        <h2 style={{ fontSize: '1.15rem', marginTop: 0, marginBottom: '1rem', color: 'var(--color-text)' }}>
          Cấu hình phân tích repository
        </h2>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem', marginBottom: '1.25rem' }}>
          {/* Repository Selection */}
          <div>
            <label style={{ display: 'block', fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.375rem' }}>
              Chọn Repository
            </label>
            <select
              value={effectiveRepoId}
              onChange={(e) => handleRepoChange(e.target.value)}
              disabled={reposLoading || loading}
              style={{
                width: '100%',
                padding: '0.625rem',
                borderRadius: '6px',
                border: '1px solid var(--color-border, #cbd5e1)',
                background: '#fff',
                fontSize: '0.9rem',
              }}
            >
              <option value="">-- Chọn repository --</option>
              {repos.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} {r.private ? '(Private)' : '(Public)'} · branch: {r.default_branch}
                </option>
              ))}
            </select>
            {selectedRepo && (
              <p style={{ margin: '0.35rem 0 0', fontSize: '0.8rem', color: 'var(--color-text-muted, #64748b)' }}>
                {selectedRepo.description || 'Không có mô tả'} · {selectedRepo.private ? '🔒 Riêng tư' : '🌐 Công khai'}
              </p>
            )}
          </div>

          {/* Scope Selection */}
          <div>
            <label style={{ display: 'block', fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.375rem' }}>
              Phạm vi phân tích (Scope)
            </label>
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value as 'all' | 'public' | 'private')}
              disabled={loading}
              style={{
                width: '100%',
                padding: '0.625rem',
                borderRadius: '6px',
                border: '1px solid var(--color-border, #cbd5e1)',
                background: '#fff',
                fontSize: '0.9rem',
              }}
            >
              <option value="all">Tất cả (All code in repo)</option>
              <option value="public">Chỉ nội dung công khai (Public)</option>
              <option value="private">Nội dung riêng tư (Private - Cần consent)</option>
            </select>
          </div>
        </div>

        {/* Advanced Options Toggle */}
        <div style={{ marginBottom: '1rem', display: 'flex', flexWrap: 'wrap', gap: '1.5rem', alignItems: 'center' }}>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={useBackgroundJob}
              onChange={(e) => setUseBackgroundJob(e.target.checked)}
              disabled={loading}
            />
            <span>Chạy nền với hàng đợi (Redis + RQ Worker)</span>
          </label>

          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={enableTimeRange}
              onChange={(e) => setEnableTimeRange(e.target.checked)}
              disabled={loading}
            />
            <span>Lọc theo mốc thời gian commit (PBI-010)</span>
          </label>
        </div>

        {/* Time range parameters if enabled */}
        {enableTimeRange && (
          <div style={{ padding: '1rem', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '1.25rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.25rem' }}>Chế độ</label>
                <select value={mode} onChange={(e) => setMode(e.target.value as 'preset' | 'month' | 'year' | 'custom')} style={{ width: '100%', padding: '0.5rem', borderRadius: 6, border: '1px solid #cbd5e1' }}>
                  <option value="preset">Khoảng gần đây</option>
                  <option value="month">Theo tháng</option>
                  <option value="year">Theo năm</option>
                  <option value="custom">Tùy chọn ngày</option>
                </select>
              </div>

              {mode === 'preset' && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.25rem' }}>Khoảng</label>
                  <select value={preset} onChange={(e) => setPreset(e.target.value)} style={{ width: '100%', padding: '0.5rem', borderRadius: 6, border: '1px solid #cbd5e1' }}>
                    <option value="1m">1 tháng</option>
                    <option value="3m">3 tháng</option>
                    <option value="6m">6 tháng</option>
                    <option value="1y">1 năm</option>
                  </select>
                </div>
              )}

              {mode === 'month' && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.25rem' }}>Tháng</label>
                  <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} style={{ width: '100%', padding: '0.5rem', borderRadius: 6, border: '1px solid #cbd5e1' }} />
                </div>
              )}

              {mode === 'year' && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.25rem' }}>Năm</label>
                  <input type="number" min="2000" max="2100" value={year} onChange={(e) => setYear(e.target.value)} style={{ width: '100%', padding: '0.5rem', borderRadius: 6, border: '1px solid #cbd5e1' }} />
                </div>
              )}

              {mode === 'custom' && (
                <>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.25rem' }}>Từ ngày</label>
                    <input type="date" value={start} onChange={(e) => setStart(e.target.value)} style={{ width: '100%', padding: '0.5rem', borderRadius: 6, border: '1px solid #cbd5e1' }} />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.25rem' }}>Đến ngày</label>
                    <input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} style={{ width: '100%', padding: '0.5rem', borderRadius: 6, border: '1px solid #cbd5e1' }} />
                  </div>
                </>
              )}

              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.25rem' }}>Múi giờ</label>
                <select value={timezone} onChange={(e) => setTimezone(e.target.value)} style={{ width: '100%', padding: '0.5rem', borderRadius: 6, border: '1px solid #cbd5e1' }}>
                  <option value="Asia/Ho_Chi_Minh">Việt Nam (UTC+7)</option>
                  <option value="UTC">UTC</option>
                  <option value="America/New_York">New York</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {/* Action Button */}
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => void handleAnalyze()}
            disabled={Boolean(loading || !effectiveRepoId || (activeJob && ['queued', 'running'].includes(activeJob.status)))}
            style={{
              padding: '0.75rem 1.5rem',
              borderRadius: '8px',
              background: 'var(--color-primary, #2563eb)',
              color: '#ffffff',
              fontWeight: 600,
              fontSize: '0.95rem',
              border: 'none',
              cursor: loading || !effectiveRepoId ? 'not-allowed' : 'pointer',
              opacity: loading || !effectiveRepoId ? 0.7 : 1,
            }}
          >
            {loading ? 'Đang phân tích...' : '🚀 Bắt đầu phân tích'}
          </button>

          {effectiveRepoId && (
            <button
              type="button"
              onClick={() => {
                const repoIdNum = Number(effectiveRepoId)
                if (repoIdNum) {
                  setLoading(true)
                  fetchLatestAnalysis(repoIdNum)
                    .then((res) => {
                      setData(res)
                      void loadEvidence(repoIdNum, res.commit_sha)
                      setError(null)
                    })
                    .catch(() => setError('Chưa có kết quả phân tích lưu trước đó.'))
                    .finally(() => setLoading(false))
                }
              }}
              disabled={loading}
              style={{
                padding: '0.75rem 1.25rem',
                borderRadius: '8px',
                background: 'transparent',
                color: 'var(--color-text, #334155)',
                fontWeight: 500,
                fontSize: '0.9rem',
                border: '1px solid var(--color-border, #cbd5e1)',
                cursor: loading ? 'not-allowed' : 'pointer',
              }}
            >
              🔄 Tải lại kết quả gần nhất
            </button>
          )}
        </div>
      </section>

      {/* Background Job Progress Card */}
      {activeJob && (
        <section className="card" style={{ marginBottom: '2rem', padding: '1.25rem', background: '#f8fafc', borderColor: '#cbd5e1' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>
              Tiến trình chạy nền (Job #{activeJob.id.slice(0, 8)})
            </h3>
            <span
              style={{
                padding: '3px 10px',
                borderRadius: '999px',
                fontSize: '0.75rem',
                fontWeight: 600,
                background:
                  activeJob.status === 'succeeded' ? '#dcfce7' : activeJob.status === 'failed' ? '#fee2e2' : '#e0e7ff',
                color:
                  activeJob.status === 'succeeded' ? '#166534' : activeJob.status === 'failed' ? '#991b1b' : '#3730a3',
              }}
            >
              {activeJob.status.toUpperCase()}
            </span>
          </div>

          <progress
            value={activeJob.progress}
            max="100"
            style={{ width: '100%', height: '10px', borderRadius: '5px', marginBottom: '0.5rem' }}
          />

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.85rem' }}>
            <span style={{ color: '#64748b' }}>
              Bước: <strong>{activeJob.step}</strong> ({activeJob.progress}%)
            </span>

            <div style={{ display: 'flex', gap: '0.5rem' }}>
              {['queued', 'running'].includes(activeJob.status) && (
                <button
                  type="button"
                  onClick={() => void handleCancelJob()}
                  disabled={jobActionBusy}
                  style={{
                    padding: '4px 10px',
                    borderRadius: 4,
                    border: '1px solid #ef4444',
                    background: '#fff',
                    color: '#ef4444',
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                  }}
                >
                  Hủy job
                </button>
              )}

              {['failed', 'cancelled'].includes(activeJob.status) && (
                <button
                  type="button"
                  onClick={() => void handleRetryJob()}
                  disabled={jobActionBusy}
                  style={{
                    padding: '4px 10px',
                    borderRadius: 4,
                    border: '1px solid #2563eb',
                    background: '#2563eb',
                    color: '#fff',
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                  }}
                >
                  Thử lại
                </button>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Error alert */}
      {error && (
        <div
          role="alert"
          style={{
            padding: '1rem',
            borderRadius: '8px',
            background: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#991b1b',
            marginBottom: '1.5rem',
            fontSize: '0.9rem',
          }}
        >
          <strong>⚠️ {errorCode ? `Lỗi ${errorCode}: ` : 'Thông báo: '}</strong>
          {error}
        </div>
      )}

      {/* Results Section */}
      {data && (
        <div style={{ display: 'grid', gap: '1.75rem' }}>
          {/* Metadata & Structure Card */}
          <section className="card" style={{ padding: '1.5rem', background: '#ffffff' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', borderBottom: '1px solid #e2e8f0', paddingBottom: '1rem', marginBottom: '1.25rem' }}>
              <div>
                <h2 style={{ margin: '0 0 0.35rem 0', fontSize: '1.3rem' }}>
                  Kết quả phân tích: {selectedRepo?.name ?? `Repo #${data.repository_id}`}
                </h2>
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap', fontSize: '0.85rem', color: '#64748b' }}>
                  <span>Commit SHA: <code style={{ background: '#f1f5f9', padding: '2px 6px', borderRadius: 4 }}>{data.commit_sha}</code></span>
                  <span>Thời gian: {new Date(data.analyzed_at).toLocaleString('vi-VN')}</span>
                  <span>Scope: <strong style={{ textTransform: 'capitalize' }}>{data.scope}</strong></span>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <span style={{ background: '#dcfce7', color: '#166534', padding: '4px 12px', borderRadius: 999, fontSize: '0.8rem', fontWeight: 600 }}>
                  ✓ Đã lưu PostgreSQL
                </span>
                <span style={{ background: '#e0e7ff', color: '#3730a3', padding: '4px 12px', borderRadius: 999, fontSize: '0.8rem', fontWeight: 600 }}>
                  {data.evidence_count} Dẫn chứng
                </span>
              </div>
            </div>

            {/* Structure metrics grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
              <div style={{ padding: '1rem', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <span style={{ fontSize: '0.8rem', color: '#64748b', display: 'block' }}>Tổng số tệp tin</span>
                <strong style={{ fontSize: '1.5rem', color: '#0f172a' }}>{data.structure.total_files}</strong>
              </div>

              <div style={{ padding: '1rem', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <span style={{ fontSize: '0.8rem', color: '#64748b', display: 'block' }}>Tệp mã nguồn đã quét</span>
                <strong style={{ fontSize: '1.5rem', color: '#16a34a' }}>{data.structure.inspected_files}</strong>
              </div>

              <div style={{ padding: '1rem', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <span style={{ fontSize: '0.8rem', color: '#64748b', display: 'block' }}>Tệp loại trừ (Vendor/Binary)</span>
                <strong style={{ fontSize: '1.5rem', color: '#64748b' }}>{data.structure.ignored_files}</strong>
              </div>

              <div style={{ padding: '1rem', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <span style={{ fontSize: '0.8rem', color: '#64748b', display: 'block' }}>Tài nguyên đã dùng (Budget)</span>
                <strong style={{ fontSize: '1.1rem', color: '#0f172a', display: 'block', marginTop: 4 }}>
                  {Math.round((Number(data.budget.inspected_bytes || 0) / 1024))} KB
                </strong>
                <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Giới hạn an toàn được tuân thủ</span>
              </div>
            </div>
          </section>

          {/* Languages Section */}
          <section className="card" style={{ padding: '1.5rem', background: '#ffffff' }}>
            <h3 style={{ margin: '0 0 1rem', fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span>💻</span> Ngôn ngữ lập trình phát hiện được
            </h3>

            {data.languages.length === 0 ? (
              <p style={{ color: '#64748b', margin: 0, fontStyle: 'italic' }}>Không phát hiện mã nguồn phù hợp.</p>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
                {data.languages.map((lang) => (
                  <div
                    key={lang.name}
                    style={{
                      padding: '1rem',
                      borderRadius: '8px',
                      border: '1px solid #e2e8f0',
                      background: lang.primary ? '#f0fdf4' : '#fafafa',
                      borderColor: lang.primary ? '#86efac' : '#e2e8f0',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <strong style={{ fontSize: '1.05rem', color: '#0f172a' }}>{lang.name}</strong>
                      {lang.primary && (
                        <span style={{ background: '#22c55e', color: '#fff', fontSize: '0.7rem', padding: '2px 8px', borderRadius: 999, fontWeight: 600 }}>
                          Chính
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#64748b', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                      {lang.percentage !== null && <span>Tỷ lệ: <strong>{lang.percentage}%</strong></span>}
                      <span>Số tệp: <strong>{lang.file_count}</strong></span>
                      {lang.bytes_count !== null && <span>Dung lượng: {Math.round(lang.bytes_count / 1024)} KB</span>}
                      <span>Dẫn chứng: {lang.evidence_count} mục</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Frameworks & Technologies Section */}
          <section className="card" style={{ padding: '1.5rem', background: '#ffffff' }}>
            <h3 style={{ margin: '0 0 1rem', fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span>⚙️</span> Frameworks & Công nghệ phát hiện
            </h3>

            {data.frameworks.length === 0 ? (
              <p style={{ color: '#64748b', margin: 0, fontStyle: 'italic' }}>Không tìm thấy manifest hoặc cấu hình framework.</p>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem' }}>
                {data.frameworks.map((fw) => (
                  <div
                    key={`${fw.name}:${fw.ecosystem}`}
                    style={{
                      padding: '1rem',
                      borderRadius: '8px',
                      border: '1px solid #e2e8f0',
                      background: '#ffffff',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.35rem' }}>
                      <strong style={{ fontSize: '1.05rem', color: '#0f172a' }}>{fw.name}</strong>
                      <span
                        style={{
                          fontSize: '0.7rem',
                          padding: '2px 8px',
                          borderRadius: 999,
                          fontWeight: 600,
                          background: fw.confidence === 'high' ? '#dcfce7' : '#fef3c7',
                          color: fw.confidence === 'high' ? '#166534' : '#92400e',
                        }}
                      >
                        Độ tin cậy: {fw.confidence}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#64748b', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                      <span>Phân loại: <strong>{fw.category}</strong></span>
                      <span>Hệ sinh thái: {fw.ecosystem}</span>
                      {fw.version && <span>Phiên bản: <code>{fw.version}</code></span>}
                      <span>Số lượng bằng chứng: {fw.evidence_count}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Architecture Findings Section */}
          <section className="card" style={{ padding: '1.5rem', background: '#ffffff' }}>
            <h3 style={{ margin: '0 0 1rem', fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span>🏛️</span> Nhận diện kiến trúc phần mềm
            </h3>

            {data.architecture.length === 0 ? (
              <p style={{ color: '#64748b', margin: 0, fontStyle: 'italic' }}>Không có đủ bằng chứng cấu trúc thư mục để suy luận mẫu kiến trúc chuẩn.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {data.architecture.map((arch) => (
                  <div
                    key={arch.pattern}
                    style={{
                      padding: '1.25rem',
                      borderRadius: '8px',
                      border: '1px solid #e2e8f0',
                      background: '#f8fafc',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <h4 style={{ margin: 0, fontSize: '1.1rem', color: '#0f172a' }}>{arch.name}</h4>
                      <span style={{ fontSize: '0.75rem', padding: '3px 8px', borderRadius: 999, background: '#e0e7ff', color: '#3730a3', fontWeight: 600 }}>
                        Độ tin cậy: {arch.confidence}
                      </span>
                    </div>
                    <p style={{ margin: '0 0 0.5rem', fontSize: '0.9rem', color: '#334155' }}>
                      {arch.description}
                    </p>
                    <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
                      Dẫn chứng cấu trúc: {arch.evidence_count} mục
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Verifiable Evidence Explorer */}
          <section className="card" style={{ padding: '1.5rem', background: '#ffffff' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <h3 style={{ margin: '0 0 0.25rem', fontSize: '1.15rem' }}>
                  Bản ghi bằng chứng có thể kiểm chứng (Verifiable Evidence)
                </h3>
                <p style={{ margin: 0, fontSize: '0.85rem', color: '#64748b' }}>
                  Mỗi kết luận đều được gắn với đường dẫn tập tin và commit SHA {data.commit_sha.slice(0, 7)}.
                </p>
              </div>

              {/* Filter pills */}
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {['all', 'language', 'framework', 'architecture', 'structure', 'dependency'].map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setEvidenceFilter(t)}
                    style={{
                      padding: '4px 10px',
                      borderRadius: '999px',
                      fontSize: '0.8rem',
                      fontWeight: 500,
                      border: '1px solid',
                      borderColor: evidenceFilter === t ? 'var(--color-primary, #2563eb)' : '#cbd5e1',
                      background: evidenceFilter === t ? 'var(--color-primary, #2563eb)' : '#fff',
                      color: evidenceFilter === t ? '#fff' : '#475569',
                      cursor: 'pointer',
                      textTransform: 'capitalize',
                    }}
                  >
                    {t === 'all' ? 'Tất cả' : t}
                  </button>
                ))}
              </div>
            </div>

            {evidenceLoading ? (
              <p style={{ color: '#64748b', fontStyle: 'italic' }}>Đang tải danh sách bằng chứng chi tiết...</p>
            ) : filteredEvidence.length === 0 ? (
              <p style={{ color: '#64748b', fontStyle: 'italic' }}>Không có bằng chứng nào thuộc phân loại này.</p>
            ) : (
              <div style={{ overflowX: 'auto', border: '1px solid #e2e8f0', borderRadius: 8 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', textAlign: 'left' }}>
                      <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Tệp nguồn (Path)</th>
                      <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Phân loại</th>
                      <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Hạng mục</th>
                      <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Nguồn dẫn chứng</th>
                      <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Độ tin cậy</th>
                      <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Giải thích</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredEvidence.slice(0, 50).map((ev, idx) => (
                      <tr key={`${ev.file_path}:${ev.finding_type}:${ev.classification}:${idx}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '0.625rem 0.75rem' }}>
                          <code style={{ background: '#f1f5f9', padding: '2px 4px', borderRadius: 4, color: '#0f172a' }}>
                            {ev.file_path || '/'}
                          </code>
                          {ev.line_number && <span style={{ color: '#94a3b8', marginLeft: 4 }}>:L{ev.line_number}</span>}
                        </td>
                        <td style={{ padding: '0.625rem 0.75rem', fontWeight: 500, color: '#0f172a' }}>
                          {ev.classification}
                        </td>
                        <td style={{ padding: '0.625rem 0.75rem', color: '#64748b', textTransform: 'capitalize' }}>
                          {ev.finding_type}
                        </td>
                        <td style={{ padding: '0.625rem 0.75rem', color: '#64748b' }}>
                          {ev.evidence_source} ({ev.detection_method})
                        </td>
                        <td style={{ padding: '0.625rem 0.75rem' }}>
                          <span
                            style={{
                              padding: '2px 6px',
                              borderRadius: 4,
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              background: ev.confidence === 'high' ? '#dcfce7' : '#fef3c7',
                              color: ev.confidence === 'high' ? '#166534' : '#92400e',
                            }}
                          >
                            {Math.round(ev.confidence_score * 100)}%
                          </span>
                        </td>
                        <td style={{ padding: '0.625rem 0.75rem', color: '#334155' }}>
                          {ev.rationale}
                          {ev.matched_content && (
                            <div style={{ marginTop: 4 }}>
                              <code style={{ fontSize: '0.75rem', color: '#0369a1', background: '#f0f9ff', padding: '1px 4px', borderRadius: 3 }}>
                                {ev.matched_content}
                              </code>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Security & Code Safety Notice */}
          <div
            style={{
              padding: '1rem',
              borderRadius: '8px',
              background: '#f0fdf4',
              border: '1px solid #bbf7d0',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              fontSize: '0.85rem',
              color: '#166534',
            }}
          >
            <span style={{ fontSize: '1.25rem' }}>🛡️</span>
            <div>
              <strong>Bảo đảm an toàn & không thực thi mã nguồn:</strong> Phân tích mã nguồn và kiến trúc hoạt động hoàn toàn bằng cách đọc cấu trúc cây thư mục và phân tích tĩnh các tệp cấu hình/manifest. Mã nguồn repository không bao giờ bị thực thi trên hệ thống.
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
