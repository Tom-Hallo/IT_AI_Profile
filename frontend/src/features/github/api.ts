import { apiFetch } from '@/shared/api/client'
import type {
  AnalysisJobInfo,
  EvidenceListResult,
  Repository,
  RepositoryAnalysisResult,
  RepositoryListResponse,
  RepositoryQueryParams,
  SyncStatusResponse,
  SyncTriggerResponse,
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
): Promise<RepositoryAnalysisResult> {
  const query = commitSha ? `?commit_sha=${encodeURIComponent(commitSha)}` : ''
  return apiFetch<RepositoryAnalysisResult>(`/repositories/${repoId}/analysis${query}`, { signal })
}

/**
 * PBI-012: Lấy danh sách bản ghi bằng chứng có thể kiểm chứng gắn với commit SHA.
 */
export function fetchAnalysisEvidence(
  repoId: number,
  commitSha?: string,
  signal?: AbortSignal,
): Promise<EvidenceListResult> {
  const query = commitSha ? `?commit_sha=${encodeURIComponent(commitSha)}` : ''
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

