/**
 * Types for PBI-009 Real GitHub Repository Synchronization.
 */

export interface Repository {
  id: number
  external_id: number
  name: string
  full_name: string
  html_url: string
  description: string | null
  private: boolean
  default_branch: string
  is_fork: boolean
  fork_source: string | null
  primary_language: string | null
  languages: Record<string, number>
  stars_count: number
  forks_count: number
  open_issues_count: number
  size_kb: number
  archived: boolean
  disabled: boolean
  pushed_at: string | null
  github_created_at: string | null
  github_updated_at: string | null
  last_synced_at: string | null
  sync_status: string
}

export interface RepositoryListResponse {
  items: Repository[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

export type SyncStatusType = 'idle' | 'running' | 'completed' | 'failed'

export interface SyncStatusResponse {
  status: SyncStatusType
  is_connected: boolean
  has_private_scope: boolean
  total_repositories: number
  last_synced_at: string | null
  error_message: string | null
}

export interface SyncTriggerResponse {
  status: string
  message: string
  job_id: string | null
}

export interface RepositoryQueryParams {
  page?: number
  per_page?: number
  visibility?: 'all' | 'public' | 'private'
  search?: string
}
