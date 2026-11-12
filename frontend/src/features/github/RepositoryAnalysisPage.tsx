import { FindingEvidenceExplorer } from './FindingEvidenceExplorer'
import { ReportSkillScores } from '@/features/scoring/ReportSkillScores'
import './RepositoryAnalysisPage.css'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { ApiError, isAbortError } from '@/shared/api/client'
import { useAuth } from '@/features/auth/useAuth'
import {
  cancelAnalysisJob,
  createAnalysisJob,
  fetchAnalysisEvidence,
  fetchAnalysisJob,
  fetchCollaborationEvidence,
  fetchLatestAnalysis,
  fetchLatestCollaboration,
  fetchRepositories,
  fetchRepositoryVerification,
  fetchVerificationEvidence,
  retryAnalysisJob,
  triggerCollaborationAnalysis,
  triggerRepositoryAnalysis,
  triggerRepositoryVerification,
} from './api'
import type {
  AnalysisJobInfo,
  CollaborationEvidenceItem,
  EvidenceItem,
  Repository,
  RepositoryAnalysisResult,
  RepositoryCollaborationResult,
  RepositoryVerificationResult,
  VerificationEvidenceItem,
} from './types'

const JOB_LABELS: Record<AnalysisJobInfo['status'], string> = {
  queued: 'Đang chờ',
  running: 'Đang phân tích',
  succeeded: 'Hoàn tất',
  failed: 'Thất bại',
  cancelled: 'Đã hủy',
  cancel_requested: 'Đang hủy',
}

export function RepositoryAnalysisPage() {
  const { repositoryId: routeRepoId } = useParams()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { user, isLoading: authLoading } = useAuth()

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

  // Active Tab: PBI-012 vs PBI-013 vs PBI-014
  const [activeTab, setActiveTab] = useState<'structure' | 'verification' | 'collaboration'>(
    searchParams.get('tab') === 'collaboration'
      ? 'collaboration'
      : searchParams.get('tab') === 'verification'
      ? 'verification'
      : 'structure',
  )

  // Verification state
  const [verificationData, setVerificationData] = useState<RepositoryVerificationResult | null>(null)
  const [verificationLoading, setVerificationLoading] = useState(false)
  const [verificationEvidence, setVerificationEvidence] = useState<VerificationEvidenceItem[]>([])
  const [verEvidenceLoading, setVerEvidenceLoading] = useState(false)
  const [verEvidenceTypeFilter, setVerEvidenceTypeFilter] = useState<string>('all')
  const [verStatusFilter, setVerStatusFilter] = useState<string>('all')

  // Collaboration & CI state
  const [collaborationData, setCollaborationData] = useState<RepositoryCollaborationResult | null>(null)
  const [collaborationLoading, setCollaborationLoading] = useState(false)
  const [collaborationLoadError, setCollaborationLoadError] = useState(false)
  const [collabPage, setCollabPage] = useState(1)
  const [collabEvidenceResult, setCollabEvidenceResult] = useState<{
    key: string
    items: CollaborationEvidenceItem[]
    total: number
    failed?: boolean
  } | null>(null)
  const [collabEvidenceTypeFilter, setCollabEvidenceTypeFilter] = useState<string>('all')
  const [collabStateFilter, setCollabStateFilter] = useState<string>('all')

  // Background Job tracking
  const [activeJob, setActiveJob] = useState<AnalysisJobInfo | null>(null)
  const [jobActionBusy, setJobActionBusy] = useState(false)

  const abortControllerRef = useRef<AbortController | null>(null)
  const verificationControllerRef = useRef<AbortController | null>(null)
  const collaborationControllerRef = useRef<AbortController | null>(null)

  useEffect(() => () => {
    abortControllerRef.current?.abort()
    verificationControllerRef.current?.abort()
    collaborationControllerRef.current?.abort()
  }, [effectiveRepoId])

  const loadEvidence = useCallback(async (repoId: number, commitSha?: string, reportId?: number, signal?: AbortSignal) => {
    setEvidenceLoading(true)
    try {
      const evRes = await fetchAnalysisEvidence(repoId, commitSha, signal, reportId)
      if (!signal?.aborted) setEvidenceList(evRes.items)
    } catch {
      if (!signal?.aborted) setEvidenceList([])
    } finally {
      if (!signal?.aborted) setEvidenceLoading(false)
    }
  }, [])

  const loadVerificationEvidence = useCallback(async (repoId: number, verificationId?: number, signal?: AbortSignal) => {
    setVerEvidenceLoading(true)
    try {
      const res = await fetchVerificationEvidence(repoId, {
        verification_id: verificationId,
        per_page: 100,
      }, signal)
      if (!signal?.aborted) setVerificationEvidence(res.items)
    } catch {
      if (!signal?.aborted) setVerificationEvidence([])
    } finally {
      if (!signal?.aborted) setVerEvidenceLoading(false)
    }
  }, [])

  const loadVerification = useCallback(async (repoId: number, reportId?: number, signal?: AbortSignal) => {
    setVerificationLoading(true)
    try {
      const ver = await fetchRepositoryVerification(repoId, signal, reportId)
      if (signal?.aborted) return
      setVerificationData(ver)
      await loadVerificationEvidence(repoId, ver.id ?? undefined, signal)
    } catch {
      if (!signal?.aborted) {
        setVerificationData(null)
        setVerificationEvidence([])
      }
    } finally {
      if (!signal?.aborted) setVerificationLoading(false)
    }
  }, [loadVerificationEvidence])

  const loadCollaboration = useCallback(async (repoId: number, signal?: AbortSignal) => {
    setCollaborationLoading(true)
    setCollaborationLoadError(false)
    try {
      const collab = await fetchLatestCollaboration(repoId, signal)
      if (signal?.aborted) return
      setCollaborationData(collab)
    } catch (err) {
      if (!signal?.aborted) {
        setCollaborationData(null)
        setCollaborationLoadError(!(err instanceof ApiError && err.status === 404))

      }
    } finally {
      if (!signal?.aborted) setCollaborationLoading(false)
    }
  }, [])

  const analysisId = collaborationData?.id
  const evidenceRepoId = collaborationData?.repository_id
  const collabEvidenceKey = `${analysisId}:${collabEvidenceTypeFilter}:${collabStateFilter}:${collabPage}`
  const visibleCollabEvidence = collabEvidenceResult?.key === collabEvidenceKey ? collabEvidenceResult : null

  useEffect(() => {
    if (activeTab !== 'collaboration' || !analysisId || evidenceRepoId !== Number(effectiveRepoId)) return
    const controller = new AbortController()
    void fetchCollaborationEvidence(evidenceRepoId, {
      analysis_id: analysisId,
      evidence_type: collabEvidenceTypeFilter,
      state: collabStateFilter,
      page: collabPage,
      per_page: 25,
    }, controller.signal).then((result) => {
      if (!controller.signal.aborted) {
        setCollabEvidenceResult({ key: collabEvidenceKey, items: result.items, total: result.total })
      }
    }).catch(() => {
      if (!controller.signal.aborted) {
        setCollabEvidenceResult({ key: collabEvidenceKey, items: [], total: 0, failed: true })
      }
    })
    return () => controller.abort()
  }, [activeTab, analysisId, evidenceRepoId, effectiveRepoId, collabEvidenceKey, collabEvidenceTypeFilter, collabStateFilter, collabPage])

  const handleTabChange = (tab: 'structure' | 'verification' | 'collaboration') => {
    setActiveTab(tab)
    const newParams = new URLSearchParams(searchParams)
    newParams.set('tab', tab)
    setSearchParams(newParams)
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

  // When repo changes, automatically attempt to fetch latest saved analysis & verification
  useEffect(() => {
    if (!user || !effectiveRepoId) return
    const repoIdNum = Number(effectiveRepoId)
    if (!repoIdNum) return

    let active = true
    const controller = new AbortController()
    fetchLatestAnalysis(repoIdNum, undefined, controller.signal)
      .then((res) => {
        if (!active) return
        setData(res)
        setError(null)
        // Also fetch evidence
        void loadEvidence(repoIdNum, res.commit_sha, res.report_id ?? undefined, controller.signal)
        void loadVerification(repoIdNum, res.report_id ?? undefined, controller.signal)
      })
      .catch(() => {
        // Not analyzed yet or no saved results - normal for fresh repo
        if (!active) return
        setData(null)
        setEvidenceList([])
        void loadVerification(repoIdNum, undefined, controller.signal)
      })

    void Promise.resolve().then(() => {
      if (!controller.signal.aborted) return loadCollaboration(repoIdNum, controller.signal)
    })

    return () => {
      active = false
      controller.abort()
    }
  }, [effectiveRepoId, user, loadEvidence, loadVerification, loadCollaboration])

  // Keep polling on transient failures and discard responses after navigating away.
  useEffect(() => {
    if (!activeJob || activeJob.repo_id !== Number(effectiveRepoId)) return
    const controller = new AbortController()
    const { signal } = controller
    let timer: ReturnType<typeof setTimeout> | undefined

    if (activeJob.status === 'succeeded' && activeJob.report_id) {
      const repoId = activeJob.repo_id
      void fetchLatestAnalysis(repoId, undefined, signal, activeJob.report_id ?? undefined)
        .then((result) => {
          if (signal.aborted) return
          setData(result)
          void loadVerification(repoId, result.report_id ?? undefined, signal)
          void loadEvidence(repoId, result.commit_sha, result.report_id ?? undefined, signal)
        })
        .catch(() => {
          if (!signal.aborted) setError('Chưa tải được báo cáo đã hoàn tất. Hãy thử mở lại repository.')
        })
    } else if (['queued', 'running', 'cancel_requested'].includes(activeJob.status)) {
      const poll = () => {
        timer = setTimeout(() => {
          void fetchAnalysisJob(activeJob.id, signal)
            .then((updated) => {
              if (!signal.aborted) setActiveJob(updated)
            })
            .catch((error: unknown) => {
              if (signal.aborted) return
              if (error instanceof ApiError && [401, 403, 404].includes(error.status ?? 0)) {
                setError('Không thể truy cập tiến trình phân tích. Hãy kiểm tra quyền GitHub.')
                return
              }
              poll()
            })
        }, 2000)
      }
      poll()
    }

    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [activeJob, effectiveRepoId, loadEvidence, loadVerification])

  const handleRepoChange = (newRepoId: string) => {
    abortControllerRef.current?.abort()
    setLoading(false)
    setEvidenceLoading(false)
    setVerEvidenceLoading(false)
    setManualRepoId(newRepoId)
    if (routeRepoId) {
      const path = newRepoId ? `/repositories/${newRepoId}/analysis` : '/analysis'
      void navigate(`${path}?tab=${activeTab}`, { replace: true })
    } else {
      setSearchParams({ repository_id: newRepoId, tab: activeTab })
    }
    setError(null)
    setData(null)
    setEvidenceList([])
    setVerificationData(null)
    setVerificationEvidence([])
    setCollaborationData(null)
    setCollabPage(1)
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
          branch: currentRepo?.default_branch ?? undefined,
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
        branch: currentRepo?.default_branch ?? undefined,
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
      if (abortController.signal.aborted) return
      setData(result)
      await loadEvidence(repoId, result.commit_sha, result.report_id ?? undefined, abortController.signal)
      if (abortController.signal.aborted) return
      void loadVerification(repoId, result.report_id ?? undefined, abortController.signal)
      void loadCollaboration(repoId, abortController.signal)
    } catch (err) {
      if (!abortController.signal.aborted && !isAbortError(err)) handleApiError(err)
    } finally {
      if (!abortController.signal.aborted) setLoading(false)
    }
  }

  const handleTriggerVerification = async () => {
    setError(null)
    setErrorCode(null)

    if (!effectiveRepoId || !/^\d+$/.test(effectiveRepoId)) {
      setError('Vui lòng chọn một repository hợp lệ để xác minh.')
      return
    }

    const repoId = Number(effectiveRepoId)
    const currentRepo = repos.find((r) => r.id === repoId)

    verificationControllerRef.current?.abort()
    const controller = new AbortController()
    verificationControllerRef.current = controller
    setVerificationLoading(true)
    try {
      const payload: {
        scope?: 'all' | 'public' | 'private'
        branch?: string
        mode?: string
        preset?: string
        month?: string
        year?: string
        start_date?: string
        end_date?: string
        timezone?: string
        force_refresh?: boolean
      } = {
        scope,
        branch: currentRepo?.default_branch ?? undefined,
        force_refresh: true,
      }

      if (enableTimeRange) {
        payload.mode = mode
        payload.timezone = timezone
        if (mode === 'preset') payload.preset = preset
        if (mode === 'month') payload.month = month
        if (mode === 'year') payload.year = year
        if (mode === 'custom') {
          payload.start_date = start
          payload.end_date = end
        }
      }

      const ver = await triggerRepositoryVerification(repoId, payload, controller.signal)
      if (controller.signal.aborted) return
      setVerificationData(ver)
      await loadVerificationEvidence(repoId, ver.id ?? undefined, controller.signal)
    } catch (err) {
      if (!controller.signal.aborted) handleApiError(err)
    } finally {
      if (!controller.signal.aborted) setVerificationLoading(false)
    }
  }

  const handleTriggerCollaboration = async () => {
    if (!effectiveRepoId) return
    setError(null)
    setErrorCode(null)

    const repoId = Number(effectiveRepoId)
    const currentRepo = repos.find((r) => r.id === repoId)

    collaborationControllerRef.current?.abort()
    const controller = new AbortController()
    collaborationControllerRef.current = controller
    setCollaborationLoading(true)
    setCollaborationLoadError(false)
    try {
      const payload: {
        branch?: string
        mode?: string
        preset?: string
        month?: string
        year?: string
        start_date?: string
        end_date?: string
        timezone?: string
        force_refresh?: boolean
      } = {
        branch: currentRepo?.default_branch ?? undefined,
        force_refresh: true,
      }

      if (enableTimeRange) {
        payload.mode = mode
        payload.timezone = timezone
        if (mode === 'preset') payload.preset = preset
        if (mode === 'month') payload.month = month
        if (mode === 'year') payload.year = year
        if (mode === 'custom') {
          payload.start_date = start
          payload.end_date = end
        }
      }

      const collab = await triggerCollaborationAnalysis(repoId, payload, controller.signal)
      if (controller.signal.aborted) return
      setCollaborationData(collab)
      setCollabPage(1)
    } catch (err) {
      if (!controller.signal.aborted) handleApiError(err)
    } finally {
      if (!controller.signal.aborted) setCollaborationLoading(false)
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
      401: backendDetail || 'Vui lòng đăng nhập hoặc liên kết lại GitHub.',
      403: backendDetail || "Repository riêng tư yêu cầu quyền OAuth 'repo'. Vui lòng cấp quyền Private.",
      404: backendDetail || 'Không tìm thấy repository hoặc bạn không có quyền truy cập.',
      422: backendDetail || 'Tham số yêu cầu phân tích không hợp lệ.',
      429: 'GitHub API đang giới hạn tần suất (Rate limit). Vui lòng thử lại sau vài phút.',
      500: backendDetail || 'Backend gặp sự cố khi đọc cây thư mục repository.',
      503: backendDetail || 'Dịch vụ phân tích tạm thời không khả dụng.',
    }

    setError(messages[status ?? 0] ?? backendDetail ?? 'Không thể thực hiện phân tích.')
  }

  const selectedRepo = repos.find((r) => String(r.id) === effectiveRepoId)

  const filteredEvidence = evidenceList.filter((e) => {
    if (evidenceFilter === 'all') return true
    return e.finding_type === evidenceFilter
  })

  if (authLoading || !user) {
    return (
      <main className="analysis-login">
        <h1>Phân tích mã nguồn</h1>
        {authLoading ? <p role="status">Đang kiểm tra phiên GitHub…</p> : (
          <p><Link to="/">Về trang chủ để đăng nhập bằng GitHub</Link></p>
        )}
      </main>
    )
  }

  return (
    <main className="repository-analysis" style={{ maxWidth: 1140, margin: '2rem auto', padding: '0 1.5rem', fontFamily: 'inherit' }}>
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
              📊 Phân tích hoạt động
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
          Chọn repository để xem ngôn ngữ, framework, kiến trúc và bằng chứng.
        </p>
      </header>

      {/* Configuration & Selection Card */}
      <section className="card" style={{ marginBottom: '2rem', padding: '1.5rem', background: 'var(--color-surface, #ffffff)' }}>
        <h2 style={{ fontSize: '1.15rem', marginTop: 0, marginBottom: '1rem', color: 'var(--color-text)' }}>
          Cấu hình phân tích repository
        </h2>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))', gap: '1rem', marginBottom: '1.25rem' }}>
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
            <span>Phân tích chạy nền</span>
          </label>

          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={enableTimeRange}
              onChange={(e) => setEnableTimeRange(e.target.checked)}
              disabled={loading}
            />
            <span>Lọc theo mốc thời gian commit</span>
          </label>
        </div>

        {/* Time range parameters if enabled */}
        {enableTimeRange && (
          <div style={{ padding: '1rem', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '1.25rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 200px), 1fr))', gap: '0.75rem' }}>
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
                      void loadEvidence(repoIdNum, res.commit_sha, res.report_id ?? undefined)
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
              {JOB_LABELS[activeJob.status]}
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

      {/* Tab Switcher: PBI-012 Structure vs PBI-013 Verification */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1.5rem', borderBottom: '2px solid #e2e8f0', paddingBottom: '0.25rem' }}>
        <button
          type="button"
          onClick={() => handleTabChange('structure')}
          style={{
            padding: '0.625rem 1.25rem',
            border: 'none',
            background: 'transparent',
            borderBottom: activeTab === 'structure' ? '3px solid var(--color-primary, #2563eb)' : '3px solid transparent',
            color: activeTab === 'structure' ? 'var(--color-primary, #2563eb)' : '#64748b',
            fontWeight: activeTab === 'structure' ? 700 : 500,
            fontSize: '1rem',
            cursor: 'pointer',
            marginBottom: -2,
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <span>🏛️</span> Mã nguồn & Kiến trúc
        </button>

        <button
          type="button"
          onClick={() => handleTabChange('verification')}
          style={{
            padding: '0.625rem 1.25rem',
            border: 'none',
            background: 'transparent',
            borderBottom: activeTab === 'verification' ? '3px solid var(--color-primary, #2563eb)' : '3px solid transparent',
            color: activeTab === 'verification' ? 'var(--color-primary, #2563eb)' : '#64748b',
            fontWeight: activeTab === 'verification' ? 700 : 500,
            fontSize: '1rem',
            cursor: 'pointer',
            marginBottom: -2,
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <span>🛡️</span> Xác minh Fork & Đóng góp
          {verificationData && (
            <span
              style={{
                fontSize: '0.75rem',
                padding: '2px 8px',
                borderRadius: 999,
                fontWeight: 600,
                background: verificationData.anti_inflation_flag
                  ? '#fef3c7'
                  : verificationData.verification_status === 'verified'
                    ? '#dcfce7'
                    : '#f1f5f9',
                color: verificationData.anti_inflation_flag
                  ? '#92400e'
                  : verificationData.verification_status === 'verified'
                    ? '#166534'
                    : '#475569',
              }}
            >
              {verificationData.anti_inflation_flag
                ? 'Anti-Inflation'
                : verificationData.verification_status.toUpperCase()}
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => handleTabChange('collaboration')}
          style={{
            padding: '0.625rem 1.25rem',
            border: 'none',
            background: 'transparent',
            borderBottom: activeTab === 'collaboration' ? '3px solid var(--color-primary, #2563eb)' : '3px solid transparent',
            color: activeTab === 'collaboration' ? 'var(--color-primary, #2563eb)' : '#64748b',
            fontWeight: activeTab === 'collaboration' ? 700 : 500,
            fontSize: '1rem',
            cursor: 'pointer',
            marginBottom: -2,
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <span>🤝</span> Cộng tác, Review & CI
          {collaborationData && (
            <span
              style={{
                fontSize: '0.75rem',
                padding: '2px 8px',
                borderRadius: 999,
                fontWeight: 600,
                background: '#dbeafe',
                color: '#1e40af',
              }}
            >
              {collaborationData.total_prs_analyzed} PRs
            </span>
          )}
        </button>
      </div>

      {/* PBI-012 Structure View */}
      {activeTab === 'structure' && (
        <>
          {data ? (
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

                {data.budget.limit_reached === true && (
                  <p className="analysis-coverage-warning" role="status">
                    {data.budget.limit_reason === 'github_tree_truncated'
                      ? 'GitHub chỉ trả về một phần cây thư mục. Các số liệu dưới đây chỉ phản ánh dữ liệu đã nhận.'
                      : 'Đã đạt giới hạn quét. Báo cáo chỉ phản ánh phần dữ liệu đã xử lý.'}
                  </p>
                )}
                {/* Structure metrics grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 180px), 1fr))', gap: '1rem' }}>
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

              {data.report_id && <ReportSkillScores key={data.report_id} repoId={data.repository_id} reportId={data.report_id} />}

              {/* Languages Section */}
              <section className="card" style={{ padding: '1.5rem', background: '#ffffff' }}>
                <h3 style={{ margin: '0 0 1rem', fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span>💻</span> Ngôn ngữ lập trình phát hiện được
                </h3>

                {data.languages.length === 0 ? (
                  <p style={{ color: '#64748b', margin: 0, fontStyle: 'italic' }}>Không phát hiện mã nguồn phù hợp.</p>
                ) : (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 240px), 1fr))', gap: '1rem' }}>
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
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: '1rem' }}>
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

              {/* PBI-015: Finding → Evidence drill-down for the current analysis report */}
              <FindingEvidenceExplorer
                key={`${effectiveRepoId}:${data.report_id ?? 'latest'}:${data.commit_sha}`}
                repositoryId={Number(effectiveRepoId)}
                reportId={data.report_id ?? undefined}
                commitSha={data.commit_sha}
              />

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
          ) : (
            <div className="card" style={{ padding: '2.5rem', textAlign: 'center', background: '#ffffff' }}>
              <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>🔍</div>
              <h3 style={{ margin: '0 0 0.5rem', fontSize: '1.2rem', color: '#0f172a' }}>
                Chưa có dữ liệu phân tích mã nguồn
              </h3>
              <p style={{ margin: '0 0 1.5rem', color: '#64748b', fontSize: '0.9rem' }}>
                Hãy nhấn nút <strong>"Bắt đầu phân tích"</strong> ở trên để quét cây thư mục, nhận diện ngôn ngữ và kiến trúc.
              </p>
            </div>
          )}
        </>
      )}

      {/* PBI-013 Verification View */}
      {activeTab === 'verification' && (
        <div style={{ display: 'grid', gap: '1.75rem' }}>
          {/* Quick Action & Re-verify Header Card */}
          <section className="card" style={{ padding: '1.25rem 1.5rem', background: '#ffffff', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
            <div>
              <h2 style={{ margin: '0 0 0.25rem', fontSize: '1.25rem', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span>🛡️</span> Xác minh Fork, Quyền sở hữu & Đóng góp thực tế
              </h2>
              <p style={{ margin: 0, fontSize: '0.875rem', color: '#64748b' }}>
                Đối chiếu tác giả commit và Pull Request với tài khoản GitHub đã xác thực. Ngăn chặn suy đoán và thổi phồng hồ sơ từ code kế thừa.
              </p>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                type="button"
                onClick={() => void handleTriggerVerification()}
                disabled={Boolean(verificationLoading || !effectiveRepoId)}
                style={{
                  padding: '0.625rem 1.25rem',
                  borderRadius: '6px',
                  background: 'var(--color-primary, #2563eb)',
                  color: '#ffffff',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  border: 'none',
                  cursor: verificationLoading || !effectiveRepoId ? 'not-allowed' : 'pointer',
                  opacity: verificationLoading || !effectiveRepoId ? 0.7 : 1,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                }}
              >
                <span>{verificationLoading ? '⏳' : '🛡️'}</span>
                {verificationLoading ? 'Đang xác minh...' : 'Xác minh đóng góp ngay'}
              </button>
            </div>
          </section>

          {verificationLoading && (
            <div className="card" style={{ padding: '3rem', textAlign: 'center', background: '#ffffff' }}>
              <div style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>🔄</div>
              <h3 style={{ margin: '0 0 0.5rem', fontSize: '1.15rem' }}>Đang thu thập và xác minh dữ liệu GitHub...</h3>
              <p style={{ margin: 0, color: '#64748b', fontSize: '0.9rem' }}>
                Đang phân tích quan hệ Fork, đối chiếu GitHub Actor ID với tác giả commit và Pull Request...
              </p>
            </div>
          )}

          {!verificationLoading && !verificationData && (
            <div className="card" style={{ padding: '3rem', textAlign: 'center', background: '#ffffff' }}>
              <div style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>🛡️</div>
              <h3 style={{ margin: '0 0 0.5rem', fontSize: '1.25rem', color: '#0f172a' }}>
                Chưa có dữ liệu xác minh đóng góp
              </h3>
              <p style={{ margin: '0 auto 1.5rem', color: '#64748b', fontSize: '0.9rem', maxWidth: 540 }}>
                Repository này chưa được chạy xác minh nguồn gốc và đóng góp thực tế. Nhấn nút bên dưới để hệ thống kiểm tra và lưu dẫn chứng vào cơ sở dữ liệu.
              </p>
              <button
                type="button"
                onClick={() => void handleTriggerVerification()}
                disabled={!effectiveRepoId}
                style={{
                  padding: '0.75rem 1.5rem',
                  borderRadius: '8px',
                  background: 'var(--color-primary, #2563eb)',
                  color: '#fff',
                  fontWeight: 600,
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                🛡️ Bắt đầu xác minh đóng góp
              </button>
            </div>
          )}

          {!verificationLoading && verificationData && (
            <>
              {/* Anti-Inflation Warning Alert Banner */}
              {verificationData.anti_inflation_flag && (
                <div
                  role="alert"
                  style={{
                    padding: '1.25rem 1.5rem',
                    borderRadius: '8px',
                    background: '#fffbeb',
                    border: '2px solid #fcd34d',
                    color: '#92400e',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '1.4rem' }}>⚠️</span>
                    <strong style={{ fontSize: '1.05rem', color: '#b45309' }}>
                      Cảnh báo chống thổi phồng hồ sơ (Anti-Inflation Protection Activated)
                    </strong>
                  </div>
                  <p style={{ margin: '0 0 0.5rem 0', fontSize: '0.92rem', lineHeight: 1.5 }}>
                    Đây là một <strong>Bản Fork</strong> ({verificationData.repository_full_name} từ {verificationData.parent_repo_name || 'kho lưu trữ gốc'}).
                    Hệ thống xác minh nhận diện <strong>bạn chưa có commit đóng góp nào</strong> được tạo từ tài khoản GitHub của bạn trong repository này.
                  </p>
                  <p style={{ margin: 0, fontSize: '0.875rem', color: '#78350f' }}>
                    Toàn bộ {verificationData.unverified_commits_count} commits kế thừa từ repository gốc được đánh dấu là <em>inherited</em> và <strong>không được tính là đóng góp cá nhân của bạn</strong> để giữ tính trung thực cho hồ sơ IT Talent AI Profile.
                  </p>
                </div>
              )}

              {/* Provenance & Ownership Identity Card */}
              <section className="card" style={{ padding: '1.5rem', background: '#ffffff' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', borderBottom: '1px solid #e2e8f0', paddingBottom: '1rem', marginBottom: '1.25rem' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                      <h3 style={{ margin: 0, fontSize: '1.3rem', color: '#0f172a' }}>
                        {verificationData.repository_full_name}
                      </h3>
                      {verificationData.is_fork ? (
                        <span style={{ padding: '3px 10px', borderRadius: 999, background: '#fef3c7', color: '#92400e', fontSize: '0.8rem', fontWeight: 600 }}>
                          🍴 Bản sao Fork
                        </span>
                      ) : (
                        <span style={{ padding: '3px 10px', borderRadius: 999, background: '#dcfce7', color: '#166534', fontSize: '0.8rem', fontWeight: 600 }}>
                          🌟 Repository Gốc (Original)
                        </span>
                      )}
                    </div>
                    <p style={{ margin: 0, fontSize: '0.85rem', color: '#64748b' }}>
                      Xác minh lúc: {new Date(verificationData.verified_at).toLocaleString('vi-VN')}
                    </p>
                  </div>

                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <span
                      style={{
                        padding: '4px 12px',
                        borderRadius: 999,
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        background:
                          verificationData.verification_status === 'verified'
                            ? '#dcfce7'
                            : verificationData.verification_status === 'no_contribution'
                              ? '#fef3c7'
                              : '#f1f5f9',
                        color:
                          verificationData.verification_status === 'verified'
                            ? '#166534'
                            : verificationData.verification_status === 'no_contribution'
                              ? '#92400e'
                              : '#475569',
                      }}
                    >
                      Trạng thái: {verificationData.verification_status.toUpperCase()}
                    </span>

                    <span style={{ padding: '4px 12px', borderRadius: 999, background: '#e0e7ff', color: '#3730a3', fontSize: '0.8rem', fontWeight: 600 }}>
                      Độ tin cậy: {verificationData.confidence.toUpperCase()}
                    </span>
                  </div>
                </div>

                {/* Provenance details grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 240px), 1fr))', gap: '1rem' }}>
                  <div style={{ padding: '1rem', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                    <span style={{ fontSize: '0.8rem', color: '#64748b', display: 'block', marginBottom: 4 }}>Vai trò sở hữu (Ownership)</span>
                    <strong style={{ fontSize: '1.05rem', color: '#0f172a' }}>
                      {verificationData.ownership_status === 'owner'
                        ? 'Chủ sở hữu repo (Owner)'
                        : verificationData.ownership_status === 'fork_owner'
                          ? 'Chủ sở hữu bản Fork (Fork Owner)'
                          : verificationData.ownership_status === 'collaborator'
                            ? 'Người cộng tác (Collaborator)'
                            : 'Không xác định (Unknown)'}
                    </strong>
                    <span style={{ display: 'block', fontSize: '0.75rem', color: '#94a3b8', marginTop: 2 }}>
                      Không đồng nghĩa với tác giả mã nguồn
                    </span>
                  </div>

                  <div style={{ padding: '1rem', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                    <span style={{ fontSize: '0.8rem', color: '#64748b', display: 'block', marginBottom: 4 }}>Repository Gốc (Parent)</span>
                    {verificationData.parent_repo_name ? (
                      <div>
                        {verificationData.parent_repo_url ? (
                          <a
                            href={verificationData.parent_repo_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ fontWeight: 600, color: '#2563eb', textDecoration: 'none' }}
                          >
                            {verificationData.parent_repo_name} ↗
                          </a>
                        ) : (
                          <strong style={{ color: '#0f172a' }}>{verificationData.parent_repo_name}</strong>
                        )}
                        <span style={{ display: 'block', fontSize: '0.75rem', color: '#16a34a', marginTop: 2 }}>
                          ✓ Metadata: {verificationData.parent_metadata_status}
                        </span>
                      </div>
                    ) : (
                      <div>
                        <strong style={{ color: '#64748b' }}>Không có (Repo độc lập)</strong>
                        <span style={{ display: 'block', fontSize: '0.75rem', color: '#94a3b8', marginTop: 2 }}>
                          Trạng thái: {verificationData.parent_metadata_status}
                        </span>
                      </div>
                    )}
                  </div>

                  <div style={{ padding: '1rem', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                    <span style={{ fontSize: '0.8rem', color: '#64748b', display: 'block', marginBottom: 4 }}>Phạm vi bao phủ (Coverage)</span>
                    <strong style={{ fontSize: '1.05rem', color: '#0f172a', textTransform: 'capitalize' }}>
                      {verificationData.coverage_status === 'complete' ? 'Đầy đủ (Complete)' : verificationData.coverage_status}
                    </strong>
                    <span style={{ display: 'block', fontSize: '0.75rem', color: '#94a3b8', marginTop: 2 }}>
                      Không suy đoán ngoài phạm vi kiểm tra
                    </span>
                  </div>

                  <div style={{ padding: '1rem', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                    <span style={{ fontSize: '0.8rem', color: '#64748b', display: 'block', marginBottom: 4 }}>Tài khoản GitHub đối chiếu</span>
                    <strong style={{ fontSize: '1.05rem', color: '#0f172a' }}>
                      {typeof verificationData.summary_data?.user_login === 'string'
                        ? `@${verificationData.summary_data.user_login}`
                        : user?.full_name || 'Tài khoản hiện tại'}
                    </strong>
                    <span style={{ display: 'block', fontSize: '0.75rem', color: '#16a34a', marginTop: 2 }}>
                      ✓ Đối chiếu actor ID OAuth bảo mật
                    </span>
                  </div>
                </div>
              </section>

              {/* Contribution Metrics Grid */}
              <section className="card" style={{ padding: '1.5rem', background: '#ffffff' }}>
                <h3 style={{ margin: '0 0 1rem', fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span>📊</span> Số liệu đóng góp thực tế đã qua xác minh
                </h3>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 200px), 1fr))', gap: '1rem' }}>
                  <div style={{ padding: '1.25rem', background: '#f0fdf4', borderRadius: 8, border: '1px solid #bbf7d0' }}>
                    <span style={{ fontSize: '0.8rem', color: '#166534', display: 'block' }}>Commits đã xác minh</span>
                    <strong style={{ fontSize: '1.75rem', color: '#15803d' }}>{verificationData.verified_commits_count}</strong>
                    <span style={{ fontSize: '0.75rem', color: '#166534', display: 'block', marginTop: 4 }}>
                      Chính bạn viết (Author verified)
                    </span>
                  </div>

                  <div style={{ padding: '1.25rem', background: '#fef2f2', borderRadius: 8, border: '1px solid #fecaca' }}>
                    <span style={{ fontSize: '0.8rem', color: '#991b1b', display: 'block' }}>Commits kế thừa / Người khác</span>
                    <strong style={{ fontSize: '1.75rem', color: '#dc2626' }}>{verificationData.unverified_commits_count}</strong>
                    <span style={{ fontSize: '0.75rem', color: '#991b1b', display: 'block', marginTop: 4 }}>
                      Kế thừa từ fork hoặc tác giả khác
                    </span>
                  </div>

                  <div style={{ padding: '1.25rem', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                    <span style={{ fontSize: '0.8rem', color: '#475569', display: 'block' }}>Pull Requests xác minh</span>
                    <strong style={{ fontSize: '1.75rem', color: '#0f172a' }}>{verificationData.verified_prs_count}</strong>
                    <span style={{ fontSize: '0.75rem', color: '#64748b', display: 'block', marginTop: 4 }}>
                      PR do chính bạn tạo & tương tác
                    </span>
                  </div>

                  <div style={{ padding: '1.25rem', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                    <span style={{ fontSize: '0.8rem', color: '#475569', display: 'block' }}>Dòng mã thực tế (+ / -)</span>
                    <strong style={{ fontSize: '1.3rem', color: '#0f172a', display: 'block', marginTop: 6 }}>
                      <span style={{ color: '#16a34a' }}>+{verificationData.verified_additions.toLocaleString()}</span>
                      <span style={{ color: '#64748b', margin: '0 4px' }}>/</span>
                      <span style={{ color: '#dc2626' }}>-{verificationData.verified_deletions.toLocaleString()}</span>
                    </strong>
                    <span style={{ fontSize: '0.75rem', color: '#64748b', display: 'block', marginTop: 4 }}>
                      Chỉ tính từ commit đã xác minh
                    </span>
                  </div>
                </div>
              </section>

              {/* Limitations & Uncertainty Notice if present */}
              {verificationData.limitations.length > 0 && (
                <div style={{ padding: '1rem 1.25rem', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: '0.85rem' }}>
                  <strong style={{ color: '#475569', display: 'block', marginBottom: '0.35rem' }}>
                    ℹ️ Giới hạn & Điểm chưa xác định được ghi nhận:
                  </strong>
                  <ul style={{ margin: 0, paddingLeft: '1.25rem', color: '#64748b' }}>
                    {verificationData.limitations.map((lim, idx) => (
                      <li key={idx}>{lim}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Verification Evidence Explorer Table */}
              <section className="card" style={{ padding: '1.5rem', background: '#ffffff' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
                  <div>
                    <h3 style={{ margin: '0 0 0.25rem', fontSize: '1.15rem' }}>
                      Bản ghi dẫn chứng xác minh (Verification Evidence)
                    </h3>
                    <p style={{ margin: 0, fontSize: '0.85rem', color: '#64748b' }}>
                      Mỗi mục commit, pull request hoặc quan hệ nguồn gốc đều được ghi nhận kèm mã định danh và lý do đối chiếu.
                    </p>
                  </div>

                  {/* Filter Buttons */}
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.8rem', color: '#64748b' }}>Lọc loại:</span>
                    {['all', 'commit', 'pull_request', 'provenance'].map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => {
                          setVerEvidenceTypeFilter(t)
                        }}
                        style={{
                          padding: '3px 8px',
                          borderRadius: '999px',
                          fontSize: '0.75rem',
                          fontWeight: 500,
                          border: '1px solid',
                          borderColor: verEvidenceTypeFilter === t ? 'var(--color-primary, #2563eb)' : '#cbd5e1',
                          background: verEvidenceTypeFilter === t ? 'var(--color-primary, #2563eb)' : '#fff',
                          color: verEvidenceTypeFilter === t ? '#fff' : '#475569',
                          cursor: 'pointer',
                          textTransform: 'capitalize',
                        }}
                      >
                        {t === 'all' ? 'Tất cả' : t === 'pull_request' ? 'Pull Request' : t}
                      </button>
                    ))}

                    <span style={{ fontSize: '0.8rem', color: '#64748b', marginLeft: '0.5rem' }}>Trạng thái:</span>
                    {['all', 'verified', 'unverified', 'unknown'].map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => {
                          setVerStatusFilter(s)
                        }}
                        style={{
                          padding: '3px 8px',
                          borderRadius: '999px',
                          fontSize: '0.75rem',
                          fontWeight: 500,
                          border: '1px solid',
                          borderColor: verStatusFilter === s ? 'var(--color-primary, #2563eb)' : '#cbd5e1',
                          background: verStatusFilter === s ? 'var(--color-primary, #2563eb)' : '#fff',
                          color: verStatusFilter === s ? '#fff' : '#475569',
                          cursor: 'pointer',
                          textTransform: 'capitalize',
                        }}
                      >
                        {s === 'all' ? 'Tất cả' : s}
                      </button>
                    ))}
                  </div>
                </div>

                {verEvidenceLoading ? (
                  <p style={{ color: '#64748b', fontStyle: 'italic' }}>Đang tải danh sách bằng chứng xác minh...</p>
                ) : verificationEvidence.filter((ev) => {
                  if (verEvidenceTypeFilter !== 'all' && ev.evidence_type !== verEvidenceTypeFilter) return false
                  if (verStatusFilter !== 'all' && ev.verification_status !== verStatusFilter) return false
                  return true
                }).length === 0 ? (
                  <p style={{ color: '#64748b', fontStyle: 'italic' }}>Không có bằng chứng nào phù hợp với bộ lọc đã chọn.</p>
                ) : (
                  <div style={{ overflowX: 'auto', border: '1px solid #e2e8f0', borderRadius: 8 }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                      <thead>
                        <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', textAlign: 'left' }}>
                          <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Loại</th>
                          <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Định danh (Identifier)</th>
                          <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Tác giả ghi nhận</th>
                          <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Thuộc tính</th>
                          <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Trạng thái</th>
                          <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Lý do đối chiếu</th>
                          <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Thời gian</th>
                        </tr>
                      </thead>
                      <tbody>
                        {verificationEvidence
                          .filter((ev) => {
                            if (verEvidenceTypeFilter !== 'all' && ev.evidence_type !== verEvidenceTypeFilter) return false
                            if (verStatusFilter !== 'all' && ev.verification_status !== verStatusFilter) return false
                            return true
                          })
                          .slice(0, 50)
                          .map((ev, idx) => (
                            <tr key={`${ev.evidence_type}:${ev.target_identifier}:${idx}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                              <td style={{ padding: '0.625rem 0.75rem', textTransform: 'capitalize', fontWeight: 500 }}>
                                {ev.evidence_type === 'pull_request' ? 'PR' : ev.evidence_type}
                              </td>
                              <td style={{ padding: '0.625rem 0.75rem' }}>
                                {ev.html_url ? (
                                  <a
                                    href={ev.html_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{ color: '#2563eb', textDecoration: 'none', fontFamily: 'monospace' }}
                                  >
                                    {ev.target_identifier.length > 10 ? ev.target_identifier.slice(0, 8) : ev.target_identifier} ↗
                                  </a>
                                ) : (
                                  <code style={{ background: '#f1f5f9', padding: '2px 4px', borderRadius: 4 }}>
                                    {ev.target_identifier.length > 10 ? ev.target_identifier.slice(0, 8) : ev.target_identifier}
                                  </code>
                                )}
                              </td>
                              <td style={{ padding: '0.625rem 0.75rem', color: '#0f172a' }}>
                                {ev.actor_login ? `@${ev.actor_login}` : '—'}
                                {ev.is_bot && (
                                  <span style={{ marginLeft: 4, background: '#f1f5f9', color: '#64748b', fontSize: '0.7rem', padding: '1px 4px', borderRadius: 3 }}>
                                    bot
                                  </span>
                                )}
                              </td>
                              <td style={{ padding: '0.625rem 0.75rem', color: '#64748b' }}>
                                {ev.is_fork_inherited && (
                                  <span style={{ color: '#b45309', fontWeight: 500, display: 'block' }}>
                                    Kế thừa từ fork
                                  </span>
                                )}
                                {ev.pr_state && (
                                  <span style={{ display: 'block' }}>
                                    PR: {ev.pr_state} {ev.pr_merged ? '(Merged ✓)' : '(Unmerged)'}
                                  </span>
                                )}
                                {ev.additions !== null && ev.deletions !== null && (
                                  <span style={{ fontSize: '0.75rem' }}>
                                    +{ev.additions} / -{ev.deletions}
                                  </span>
                                )}
                              </td>
                              <td style={{ padding: '0.625rem 0.75rem' }}>
                                <span
                                  style={{
                                    padding: '2px 6px',
                                    borderRadius: 4,
                                    fontSize: '0.75rem',
                                    fontWeight: 600,
                                    background:
                                      ev.verification_status === 'verified'
                                        ? '#dcfce7'
                                        : ev.verification_status === 'unverified'
                                          ? '#fee2e2'
                                          : '#f1f5f9',
                                    color:
                                      ev.verification_status === 'verified'
                                        ? '#166534'
                                        : ev.verification_status === 'unverified'
                                          ? '#991b1b'
                                          : '#475569',
                                  }}
                                >
                                  {ev.verification_status}
                                </span>
                              </td>
                              <td style={{ padding: '0.625rem 0.75rem', color: '#334155' }}>
                                {ev.rationale}
                              </td>
                              <td style={{ padding: '0.625rem 0.75rem', color: '#64748b', whiteSpace: 'nowrap' }}>
                                {ev.recorded_at ? new Date(ev.recorded_at).toLocaleDateString('vi-VN') : '—'}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              {/* Ethical AI and Anti-Speculation Statement */}
              <div
                style={{
                  padding: '1rem',
                  borderRadius: '8px',
                  background: '#f8fafc',
                  border: '1px solid #cbd5e1',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  fontSize: '0.85rem',
                  color: '#475569',
                }}
              >
                <span style={{ fontSize: '1.25rem' }}>⚖️</span>
                <div>
                  <strong>Nguyên tắc đạo đức & chống suy đoán:</strong> Hệ thống IT Talent AI Profile tuân thủ nguyên tắc xử lý thiếu dữ liệu là <em>unknown</em> thay vì suy đoán tự khẳng định. Việc sở hữu một bản fork hay repository không bao giờ được quy đồng là tác giả của toàn bộ mã nguồn.
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* PBI-014 Collaboration, Review, CI & Problem Solving View */}
      {activeTab === 'collaboration' && (
        <div style={{ display: 'grid', gap: '1.75rem' }}>
          {/* Header Action Card */}
          <section
            className="card"
            style={{
              padding: '1.25rem 1.5rem',
              background: '#ffffff',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '1rem',
            }}
          >
            <div>
              <h2
                style={{
                  margin: '0 0 0.25rem',
                  fontSize: '1.25rem',
                  color: '#0f172a',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <span>🤝</span> Phân tích Pull Request, Review, CI & Xử lý lỗi
              </h2>
              <p style={{ margin: 0, fontSize: '0.875rem', color: '#64748b' }}>
                Thu thập và đánh giá hoạt động cộng tác, lịch sử code review, kết quả CI/CD và chu kỳ giải quyết vấn đề từ GitHub API thực tế.
              </p>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                type="button"
                onClick={() => void handleTriggerCollaboration()}
                disabled={Boolean(collaborationLoading || !effectiveRepoId)}
                style={{
                  padding: '0.625rem 1.25rem',
                  borderRadius: '6px',
                  border: 'none',
                  background: 'var(--color-primary, #2563eb)',
                  color: '#ffffff',
                  fontWeight: 600,
                  fontSize: '0.875rem',
                  cursor: collaborationLoading || !effectiveRepoId ? 'not-allowed' : 'pointer',
                  opacity: collaborationLoading || !effectiveRepoId ? 0.6 : 1,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <span>{collaborationLoading ? '⏳' : '🔄'}</span>
                {collaborationLoading ? 'Đang phân tích...' : 'Làm mới / Phân tích Cộng tác'}
              </button>
            </div>
          </section>

          {/* Objective Evaluation Non-Penalization Banner */}
          <div
            style={{
              padding: '1rem 1.25rem',
              borderRadius: '8px',
              background: '#f0fdf4',
              border: '1px solid #86efac',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.75rem',
              color: '#166534',
              fontSize: '0.875rem',
              lineHeight: 1.5,
            }}
          >
            <span style={{ fontSize: '1.25rem', marginTop: '0.1rem' }}>💡</span>
            <div>
              <strong>Nguyên tắc đánh giá khách quan & không suy diễn tiêu cực:</strong>
              <div style={{ marginTop: '0.25rem' }}>
                Hệ thống IT Talent AI Profile <strong>tuyệt đối không tự động coi các Pull Request đóng chưa merge hoặc kiểm tra CI thất bại là biểu hiện năng lực kém</strong>.
                Trong quy trình phát triển hiện đại, kiểm tra CI thất bại là cơ chế phát hiện sớm vấn đề (fail-fast) và yêu cầu thay đổi (CHANGES_REQUESTED) là một phần tự nhiên của quy trình phản biện mã nguồn chuyên nghiệp.
              </div>
            </div>
          </div>

          {collaborationLoadError && !collaborationLoading && (
            <p className="analysis-coverage-warning" role="alert">
              Không tải được báo cáo cộng tác đã lưu. Bạn có thể thử mở lại hoặc chạy phân tích.
            </p>
          )}

          {!collaborationData && !collaborationLoading && !collaborationLoadError && (
            <section
              className="card"
              style={{
                padding: '3rem 1.5rem',
                background: '#ffffff',
                textAlign: 'center',
                color: '#64748b',
              }}
            >
              <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>🤝</div>
              <h3 style={{ margin: '0 0 0.5rem', fontSize: '1.125rem', color: '#1e293b' }}>
                Chưa có dữ liệu phân tích cộng tác & CI
              </h3>
              <p style={{ margin: '0 0 1.25rem', fontSize: '0.875rem', maxWidth: '500px', marginInline: 'auto' }}>
                Nhấn vào nút <strong>&quot;Làm mới / Phân tích Cộng tác&quot;</strong> phía trên để truy xuất các Pull Request, đánh giá review, kết quả CI checks và chu kỳ xử lý lỗi.
              </p>
              <button
                type="button"
                onClick={() => void handleTriggerCollaboration()}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  background: '#ffffff',
                  fontWeight: 600,
                  fontSize: '0.875rem',
                  cursor: 'pointer',
                }}
              >
                Bắt đầu phân tích ngay
              </button>
            </section>
          )}

          {collaborationData && (
            <>
              {collaborationData.coverage_status !== 'complete' && (
                <section className="analysis-coverage-warning" aria-label="Phạm vi dữ liệu cộng tác">
                  <strong>Dữ liệu cộng tác chưa đầy đủ</strong>
                  {collaborationData.limitations?.length > 0 && (
                    <ul>{collaborationData.limitations.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
                  )}
                </section>
              )}
              {/* Summary Metrics Grid */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 240px), 1fr))',
                  gap: '1rem',
                }}
              >
                {/* PR Metrics Card */}
                <div className="card" style={{ padding: '1.25rem', background: '#ffffff' }}>
                  <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600, marginBottom: '0.5rem' }}>
                    PULL REQUESTS ({collaborationData.total_prs_analyzed})
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.875rem', color: '#334155' }}>Đã Merge:</span>
                    <strong style={{ color: '#16a34a' }}>{collaborationData.merged_prs_count}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.875rem', color: '#334155' }}>Đóng chưa merge:</span>
                    <strong style={{ color: '#64748b' }}>{collaborationData.closed_unmerged_prs_count}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.875rem', color: '#334155' }}>Đang mở (Open):</span>
                    <strong style={{ color: '#2563eb' }}>{collaborationData.open_prs_count}</strong>
                  </div>
                  <div style={{ paddingTop: '0.5rem', borderTop: '1px solid #f1f5f9', fontSize: '0.75rem', color: '#64748b' }}>
                    Của bạn: {collaborationData.user_prs_count} | Cộng sự: {collaborationData.external_prs_count}
                  </div>
                </div>

                {/* Reviews Metrics Card */}
                <div className="card" style={{ padding: '1.25rem', background: '#ffffff' }}>
                  <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600, marginBottom: '0.5rem' }}>
                    CODE REVIEWS ({collaborationData.total_reviews_analyzed})
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.875rem', color: '#334155' }}>Phê duyệt (Approved):</span>
                    <strong style={{ color: '#16a34a' }}>{collaborationData.approved_reviews_count}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.875rem', color: '#334155' }}>Yêu cầu điều chỉnh:</span>
                    <strong style={{ color: '#d97706' }}>{collaborationData.changes_requested_count}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.875rem', color: '#334155' }}>Thảo luận (Comments):</span>
                    <strong style={{ color: '#2563eb' }}>{collaborationData.commented_reviews_count}</strong>
                  </div>
                  <div style={{ paddingTop: '0.5rem', borderTop: '1px solid #f1f5f9', fontSize: '0.75rem', color: '#64748b' }}>
                    Bạn thực hiện: {collaborationData.user_reviews_conducted_count} | Nhận được: {collaborationData.user_reviews_received_count}
                  </div>
                </div>

                {/* CI & Checks Metrics Card */}
                <div className="card" style={{ padding: '1.25rem', background: '#ffffff' }}>
                  <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600, marginBottom: '0.5rem' }}>
                    KIỂM TRA CI / CHECKS ({collaborationData.total_checks_analyzed})
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.875rem', color: '#334155' }}>Thành công (Passed):</span>
                    <strong style={{ color: '#16a34a' }}>{collaborationData.successful_checks_count}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.875rem', color: '#334155' }}>Thất bại (Fail-fast):</span>
                    <strong style={{ color: '#dc2626' }}>{collaborationData.failed_checks_count}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.875rem', color: '#334155' }}>Đang chạy / Khác:</span>
                    <strong style={{ color: '#64748b' }}>{collaborationData.pending_checks_count + collaborationData.other_checks_count}</strong>
                  </div>
                  <div style={{ paddingTop: '0.5rem', borderTop: '1px solid #f1f5f9', fontSize: '0.75rem', color: '#64748b' }}>
                    Độ tin cậy: {collaborationData.confidence.toUpperCase()} | Bao phủ: {collaborationData.coverage_status}
                  </div>
                </div>

                {/* Problem-Solving Cycles Card */}
                <div className="card" style={{ padding: '1.25rem', background: '#ffffff' }}>
                  <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600, marginBottom: '0.5rem' }}>
                    XỬ LÝ LỖI & PHẢN HỒI LẶP
                  </div>
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--color-primary, #2563eb)', margin: '0.25rem 0' }}>
                    {collaborationData.problem_solving_sequences_count}
                  </div>
                  <p style={{ margin: 0, fontSize: '0.75rem', color: '#64748b', lineHeight: 1.4 }}>
                    Chu kỳ ghi nhận bằng chứng về tiếp thu review hoặc giải quyết lỗi CI qua các commit điều chỉnh.
                  </p>
                </div>
              </div>

              {/* Problem-Solving Sequences Section */}
              {collaborationData.problem_solving_sequences && collaborationData.problem_solving_sequences.length > 0 && (
                <section className="card" style={{ padding: '1.5rem', background: '#ffffff' }}>
                  <h3 style={{ margin: '0 0 1rem', fontSize: '1.125rem', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span>🔄</span> Chu kỳ giải quyết vấn đề & phản hồi lặp được xác minh
                  </h3>
                  <div style={{ display: 'grid', gap: '1rem' }}>
                    {collaborationData.problem_solving_sequences.map((seq) => (
                      <div
                        key={seq.sequence_id}
                        style={{
                          padding: '1rem',
                          borderRadius: '8px',
                          border: '1px solid #e2e8f0',
                          background: '#f8fafc',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                          <span style={{ fontWeight: 600, color: '#1e293b', fontSize: '0.9rem' }}>
                            {seq.sequence_id} {seq.pr_number ? `(PR #${seq.pr_number})` : ''}
                          </span>
                          <span style={{ fontSize: '0.75rem', padding: '2px 8px', borderRadius: 999, background: '#dcfce7', color: '#166534', fontWeight: 600 }}>
                            Chu kỳ hoàn tất
                          </span>
                        </div>
                        <p style={{ margin: '0 0 0.75rem', fontSize: '0.85rem', color: '#334155' }}>
                          {seq.explanation}
                        </p>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', fontSize: '0.75rem', color: '#64748b' }}>
                          <span><strong>Khởi phát:</strong> {String(seq.trigger_event?.type || '')}</span>
                          <span>&rarr;</span>
                          <span><strong>Điều chỉnh:</strong> Commit hiệu chỉnh</span>
                          <span>&rarr;</span>
                          <span><strong>Kết quả:</strong> {String(seq.resolution_or_outcome?.type || '')}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Contextual Collaboration Observations */}
              {collaborationData.collaboration_observations && collaborationData.collaboration_observations.length > 0 && (
                <section className="card" style={{ padding: '1.5rem', background: '#ffffff' }}>
                  <h3 style={{ margin: '0 0 1rem', fontSize: '1.125rem', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span>🔍</span> Quan sát hợp tác & phản biện dựa trên bằng chứng
                  </h3>
                  <div style={{ display: 'grid', gap: '0.75rem' }}>
                    {collaborationData.collaboration_observations.map((obs, idx) => (
                      <div
                        key={idx}
                        style={{
                          padding: '0.875rem 1rem',
                          borderRadius: '6px',
                          borderLeft: '4px solid var(--color-primary, #2563eb)',
                          background: '#f8fafc',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                          <strong style={{ fontSize: '0.9rem', color: '#0f172a' }}>{obs.title}</strong>
                          <span style={{ fontSize: '0.7rem', padding: '2px 6px', borderRadius: 4, background: '#e2e8f0', color: '#475569', textTransform: 'uppercase' }}>
                            {obs.evidence_level}
                          </span>
                        </div>
                        <p style={{ margin: 0, fontSize: '0.85rem', color: '#475569', lineHeight: 1.5 }}>
                          {obs.description}
                        </p>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Verifiable Collaboration Evidence Table */}
              <section className="card" style={{ padding: '1.5rem', background: '#ffffff' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: '1.125rem', color: '#0f172a' }}>
                      📋 Nhật ký bằng chứng chi tiết (Audit Trail)
                    </h3>
                    <p style={{ margin: '0.25rem 0 0', fontSize: '0.85rem', color: '#64748b' }}>
                      Lọc bằng chứng PR, review và CI trong báo cáo đang xem.
                    </p>
                  </div>

                  {/* Filters */}
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <select
                      value={collabEvidenceTypeFilter}
                      aria-label="Loại bằng chứng"
                      onChange={(e) => { setCollabEvidenceTypeFilter(e.target.value); setCollabPage(1) }}
                      style={{ padding: '0.375rem 0.625rem', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: '0.8rem' }}
                    >
                      <option value="all">Tất cả loại bằng chứng</option>
                      <option value="pull_request">Pull Request</option>
                      <option value="review">Code Review</option>
                      <option value="check_run">Check Run (Checks API)</option>
                      <option value="commit_status">Commit Status (Status API)</option>
                      <option value="problem_solving_sequence">Chu kỳ xử lý lỗi</option>
                    </select>

                    <select
                      value={collabStateFilter}
                      aria-label="Trạng thái bằng chứng"
                      onChange={(e) => { setCollabStateFilter(e.target.value); setCollabPage(1) }}
                      style={{ padding: '0.375rem 0.625rem', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: '0.8rem' }}
                    >
                      <option value="all">Tất cả trạng thái</option>
                      <option value="merged">Merged</option>
                      <option value="closed_unmerged">Closed unmerged</option>
                      <option value="open">Open</option>
                      <option value="APPROVED">Approved</option>
                      <option value="CHANGES_REQUESTED">Changes Requested</option>
                      <option value="success">CI thành công</option>
                      <option value="completed">CI đã kết thúc</option>
                      <option value="pending">CI đang chờ</option>
                      <option value="failure">CI thất bại</option>
                    </select>
                  </div>
                </div>

                {analysisId && !visibleCollabEvidence ? (
                  <p style={{ color: '#64748b', fontSize: '0.875rem' }}>Đang tải danh sách bằng chứng...</p>
                ) : visibleCollabEvidence?.failed ? (
                  <p role="alert">Không tải được bằng chứng. Hãy đổi bộ lọc hoặc mở lại báo cáo.</p>
                ) : !visibleCollabEvidence?.items.length ? (
                  <p style={{ color: '#64748b', fontSize: '0.875rem' }}>Không có bằng chứng nào phù hợp với bộ lọc.</p>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                      <thead>
                        <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', textAlign: 'left' }}>
                          <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Loại</th>
                          <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Định danh đối tượng</th>
                          <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Trạng thái</th>
                          <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Tác giả / Diễn viên</th>
                          <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Giải trình khách quan</th>
                          <th style={{ padding: '0.625rem 0.75rem', fontWeight: 600 }}>Thời gian</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleCollabEvidence.items
                          .map((ev, idx) => (
                            <tr key={`${ev.evidence_type}:${ev.target_identifier}:${idx}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                              <td style={{ padding: '0.625rem 0.75rem', textTransform: 'capitalize', fontWeight: 500 }}>
                                {ev.evidence_type === 'pull_request' ? 'PR' : ev.evidence_type}
                              </td>
                              <td style={{ padding: '0.625rem 0.75rem' }}>
                                {ev.html_url ? (
                                  <a
                                    href={ev.html_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    style={{ color: 'var(--color-primary, #2563eb)', textDecoration: 'none', fontWeight: 600 }}
                                  >
                                    {ev.target_identifier} ↗
                                  </a>
                                ) : (
                                  <span style={{ fontWeight: 600 }}>{ev.target_identifier}</span>
                                )}
                              </td>
                              <td style={{ padding: '0.625rem 0.75rem' }}>
                                <span
                                  style={{
                                    padding: '2px 8px',
                                    borderRadius: 999,
                                    fontSize: '0.75rem',
                                    fontWeight: 600,
                                    background:
                                      ev.state === 'merged' || ev.conclusion === 'success' || ev.state === 'APPROVED'
                                        ? '#dcfce7'
                                        : ev.state === 'closed_unmerged' || ev.state === 'CHANGES_REQUESTED'
                                          ? '#fef3c7'
                                          : ev.conclusion === 'failure' || ev.state === 'failure'
                                            ? '#fee2e2'
                                            : '#f1f5f9',
                                    color:
                                      ev.state === 'merged' || ev.conclusion === 'success' || ev.state === 'APPROVED'
                                        ? '#166534'
                                        : ev.state === 'closed_unmerged' || ev.state === 'CHANGES_REQUESTED'
                                          ? '#92400e'
                                          : ev.conclusion === 'failure' || ev.state === 'failure'
                                            ? '#991b1b'
                                            : '#475569',
                                  }}
                                >
                                  {ev.conclusion || ev.state || 'N/A'}
                                </span>
                              </td>
                              <td style={{ padding: '0.625rem 0.75rem', color: '#475569' }}>
                                {ev.actor_login ? `@${ev.actor_login}` : '—'}
                                {ev.is_profile_owner && (
                                  <span style={{ marginLeft: 4, fontSize: '0.7rem', padding: '1px 4px', background: '#e0e7ff', color: '#3730a3', borderRadius: 4 }}>
                                    Bạn
                                  </span>
                                )}
                              </td>
                              <td style={{ padding: '0.625rem 0.75rem', color: '#334155', maxWidth: '350px' }}>
                                {ev.rationale}
                              </td>
                              <td style={{ padding: '0.625rem 0.75rem', color: '#64748b', whiteSpace: 'nowrap' }}>
                                {ev.recorded_at ? new Date(ev.recorded_at).toLocaleDateString('vi-VN') : '—'}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                    {visibleCollabEvidence.total > 25 && (
                      <nav aria-label="Phân trang bằng chứng cộng tác">
                        <button type="button" disabled={collabPage === 1} onClick={() => setCollabPage(page => page - 1)}>Trang trước</button>
                        <span aria-live="polite"> Trang {collabPage} / {Math.ceil(visibleCollabEvidence.total / 25)} </span>
                        <button type="button" disabled={collabPage * 25 >= visibleCollabEvidence.total} onClick={() => setCollabPage(page => page + 1)}>Trang sau</button>
                      </nav>
                    )}
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      )}
    </main>
  )
}
