import { apiFetch } from '@/shared/api/client'
import type {
  AnalysisJobInfo,
  CollaborationEvidenceListResult,
  EvidenceListResult,
  Repository,
  RepositoryAnalysisResult,
  RepositoryCollaborationResult,
  RepositoryListResponse,
  RepositoryQueryParams,
  RepositoryVerificationResult,
  SyncStatusResponse,
  SyncTriggerResponse,
  VerificationEvidenceListResult,
} from './types'

/**
 * Lấy trạng thái đồng bộ GitHub hiện tại của người dùng.
 */
export function fetchSyncStatus(signal?: AbortSignal): Promise<SyncStatusResponse> {
  return apiFetch<SyncStatusResponse>('/github/sync/status', { signal })
}

/**
 * Kích hoạt đồng bộ repository GitHub.
 * Mặc định kích hoạt background worker qua Redis + RQ.
 */
export function triggerSync(background = true): Promise<SyncTriggerResponse> {
  return apiFetch<SyncTriggerResponse>(`/github/sync?background=${background}`, {
    method: 'POST',
  })
}

/**
 * Lấy danh sách repositories đã đồng bộ với bộ lọc và phân trang.
 */
export function fetchRepositories(
  params: RepositoryQueryParams = {},
  signal?: AbortSignal,
): Promise<RepositoryListResponse> {
  const query = new URLSearchParams()
  if (params.page !== undefined) query.set('page', String(params.page))
  if (params.per_page !== undefined) query.set('per_page', String(params.per_page))
  if (params.visibility && params.visibility !== 'all') query.set('visibility', params.visibility)
  if (params.search?.trim()) query.set('search', params.search.trim())

  const queryString = query.toString()
  const path = queryString ? `/github/repositories?${queryString}` : '/github/repositories'

  return apiFetch<RepositoryListResponse>(path, { signal })
}

/**
 * Lấy chi tiết một repository theo ID nội bộ.
 */
export function fetchRepository(id: number, signal?: AbortSignal): Promise<Repository> {
  return apiFetch<Repository>(`/github/repositories/${id}`, { signal })
}

/**
 * Hủy liên kết tài khoản GitHub và xóa OAuth token đã mã hóa.
 */
export function disconnectGitHub(): Promise<{ disconnected: boolean; message: string }> {
  return apiFetch<{ disconnected: boolean; message: string }>('/auth/github/disconnect', {
    method: 'POST',
  })
}

/**
 * PBI-012: Kích hoạt phân tích tĩnh mã nguồn, framework & kiến trúc repository đồng bộ.
 */
export function triggerRepositoryAnalysis(
  repoId: number,
  payload: {
    scope?: 'all' | 'public' | 'private' | 'full'
    branch?: string
    mode?: string
    preset?: string
    month?: string
    year?: string | number
    start_date?: string
    end_date?: string
    timezone?: string
  } = {},
  signal?: AbortSignal,
): Promise<RepositoryAnalysisResult> {
  return apiFetch<RepositoryAnalysisResult>(`/repositories/${repoId}/analyze`, {
    method: 'POST',
    body: payload,
    signal,
    timeoutMs: 60000,
  })
}

/**
 * PBI-012: Lấy kết quả phân tích gần nhất đã lưu trong DB.
 */
export function fetchLatestAnalysis(
  repoId: number,
  commitSha?: string,
  signal?: AbortSignal,
  reportId?: number,
): Promise<RepositoryAnalysisResult> {
  const query = reportId ? `?report_id=${reportId}` : commitSha ? `?commit_sha=${encodeURIComponent(commitSha)}` : ''
  return apiFetch<RepositoryAnalysisResult>(`/repositories/${repoId}/analysis${query}`, { signal })
}

/**
 * PBI-012: Lấy danh sách bản ghi bằng chứng có thể kiểm chứng gắn với commit SHA.
 */
export function fetchAnalysisEvidence(
  repoId: number,
  commitSha?: string,
  signal?: AbortSignal,
  reportId?: number,
): Promise<EvidenceListResult> {
  const query = reportId ? `?report_id=${reportId}` : commitSha ? `?commit_sha=${encodeURIComponent(commitSha)}` : ''
  return apiFetch<EvidenceListResult>(`/repositories/${repoId}/analysis/evidence${query}`, { signal })
}

/**
 * PBI-011: Tạo background analysis job chạy qua Redis + RQ.
 */
export function createAnalysisJob(
  repoId: number,
  payload:
    | string
    | {
        scope?: string
        branch?: string
        mode?: string
        preset?: string
        month?: string
        year?: string | number
        start_date?: string
        end_date?: string
        timezone?: string
      } = 'full',
): Promise<AnalysisJobInfo> {
  const body =
    typeof payload === 'string'
      ? { repo_id: repoId, scope: payload }
      : { repo_id: repoId, ...payload }

  return apiFetch<AnalysisJobInfo>('/analysis/jobs', {
    method: 'POST',
    body,
  })
}

/**
 * PBI-011: Lấy thông tin trạng thái tiến độ job phân tích nền.
 */
export function fetchAnalysisJob(jobId: string, signal?: AbortSignal): Promise<AnalysisJobInfo> {
  return apiFetch<AnalysisJobInfo>(`/analysis/jobs/${jobId}`, { signal })
}

/**
 * PBI-011: Hủy bỏ job phân tích đang chạy.
 */
export function cancelAnalysisJob(jobId: string): Promise<AnalysisJobInfo> {
  return apiFetch<AnalysisJobInfo>(`/analysis/jobs/${jobId}/cancel`, {
    method: 'POST',
  })
}

/**
 * PBI-011: Thử lại job phân tích đã thất bại hoặc đã hủy.
 */
export function retryAnalysisJob(jobId: string): Promise<AnalysisJobInfo> {
  return apiFetch<AnalysisJobInfo>(`/analysis/jobs/${jobId}/retry`, {
    method: 'POST',
  })
}

/**
 * PBI-013: Lấy kết quả xác minh fork, ownership và đóng góp thực tế gần nhất.
 */
export function fetchRepositoryVerification(
  repoId: number,
  signal?: AbortSignal,
  reportId?: number,
): Promise<RepositoryVerificationResult> {
  const query = reportId ? `?report_id=${reportId}` : ''
  return apiFetch<RepositoryVerificationResult>(`/repositories/${repoId}/verification${query}`, { signal })
}

/**
 * PBI-013: Kích hoạt / làm mới xác minh fork, ownership & đóng góp từ GitHub API.
 */
export function triggerRepositoryVerification(
  repoId: number,
  payload: {
    branch?: string
    mode?: string
    preset?: string
    month?: string
    year?: string | number
    start_date?: string
    end_date?: string
    timezone?: string
    force_refresh?: boolean
  } = {},
  signal?: AbortSignal,
): Promise<RepositoryVerificationResult> {
  return apiFetch<RepositoryVerificationResult>(`/repositories/${repoId}/verification`, {
    method: 'POST',
    body: payload,
    signal,
    timeoutMs: 60000,
  })
}

/**
 * PBI-013: Truy xuất danh sách bằng chứng xác minh phân trang và lọc theo trạng thái/loại.
 */
export function fetchVerificationEvidence(
  repoId: number,
  params: {
    verification_id?: number
    verification_status?: string
    evidence_type?: string
    page?: number
    per_page?: number
  } = {},
  signal?: AbortSignal,
): Promise<VerificationEvidenceListResult> {
  const query = new URLSearchParams()
  if (params.verification_id) query.set('verification_id', String(params.verification_id))
  if (params.verification_status && params.verification_status !== 'all') {
    query.set('verification_status', params.verification_status)
  }
  if (params.evidence_type && params.evidence_type !== 'all') {
    query.set('evidence_type', params.evidence_type)
  }
  if (params.page !== undefined) query.set('page', String(params.page))
  if (params.per_page !== undefined) query.set('per_page', String(params.per_page))

  const qs = query.toString() ? `?${query.toString()}` : ''
  return apiFetch<VerificationEvidenceListResult>(
    `/repositories/${repoId}/verification/evidence${qs}`,
    { signal },
  )
}

/**
 * PBI-014: Kích hoạt / làm mới phân tích Pull Request, Review, CI & xử lý lỗi.
 */
export function triggerCollaborationAnalysis(
  repoId: number,
  payload: {
    branch?: string
    mode?: string
    preset?: string
    month?: string
    year?: string | number
    start_date?: string
    end_date?: string
    timezone?: string
    force_refresh?: boolean
  } = {},
  signal?: AbortSignal,
): Promise<RepositoryCollaborationResult> {
  return apiFetch<RepositoryCollaborationResult>(`/repositories/${repoId}/collaboration`, {
    method: 'POST',
    body: payload,
    signal,
    timeoutMs: 60000,
  })
}

/**
 * PBI-014: Lấy kết quả phân tích cộng tác gần nhất đã lưu trong DB.
 */
export function fetchLatestCollaboration(
  repoId: number,
  signal?: AbortSignal,
): Promise<RepositoryCollaborationResult> {
  return apiFetch<RepositoryCollaborationResult>(`/repositories/${repoId}/collaboration`, {
    signal,
  })
}

/**
 * PBI-014: Truy xuất danh sách bằng chứng cộng tác phân trang và lọc theo trạng thái/loại.
 */
export function fetchCollaborationEvidence(
  repoId: number,
  params: {
    evidence_type?: string
    state?: string
    pr_number?: number
    page?: number
    per_page?: number
  } = {},
  signal?: AbortSignal,
): Promise<CollaborationEvidenceListResult> {
  const query = new URLSearchParams()
  if (params.evidence_type && params.evidence_type !== 'all') {
    query.set('evidence_type', params.evidence_type)
  }
  if (params.state && params.state !== 'all') {
    query.set('state', params.state)
  }
  if (params.pr_number !== undefined) {
    query.set('pr_number', String(params.pr_number))
  }
  if (params.page !== undefined) query.set('page', String(params.page))
  if (params.per_page !== undefined) query.set('per_page', String(params.per_page))

  const qs = query.toString() ? `?${query.toString()}` : ''
  return apiFetch<CollaborationEvidenceListResult>(
    `/repositories/${repoId}/collaboration/evidence${qs}`,
    { signal },
  )
}


// PBI-015: Finding → Evidence. Backend responses deliberately omit raw snippets.
export interface FindingSummary {
  id: number
  report_id: number
  finding_type: string
  classification: string
  confidence_score: number
  analyzer_version: string
}

export interface FindingEvidence {
  id: number
  commit_sha: string
  file_path: string
  line_number: number | null
  evidence_source: string
  detection_method: string
  confidence_score: number
}

export interface FindingDetail extends FindingSummary {
  repository_id: number
  commit_sha: string
  rationale: string
  scope: string
  time_range: Record<string, unknown> | null
  evidence: FindingEvidence[]
}

export function fetchFindings(repoId: number, reportId?: number, signal?: AbortSignal): Promise<FindingSummary[]> {
  const query = new URLSearchParams({ repository_id: String(repoId), limit: '200' })
  if (reportId !== undefined) query.set('report_id', String(reportId))
  return apiFetch<FindingSummary[]>(`/analysis/findings?${query.toString()}`, { signal })
}

export function fetchFindingDetail(findingId: number, signal?: AbortSignal): Promise<FindingDetail> {
  return apiFetch<FindingDetail>(`/analysis/findings/${findingId}`, { signal })
}
