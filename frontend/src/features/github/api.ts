import { apiFetch } from '@/shared/api/client'
import type {
  Repository,
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
