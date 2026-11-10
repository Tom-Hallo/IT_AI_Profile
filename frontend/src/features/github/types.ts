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

/**
 * Types for PBI-012 Repository Code, Language, Framework & Architecture Analysis.
 */

export interface LanguageFinding {
  name: string
  primary: boolean
  bytes_count: number | null
  percentage: number | null
  file_count: number
  evidence_count: number
}

export interface FrameworkFinding {
  name: string
  category: string
  ecosystem: string
  version: string | null
  status: string
  confidence: string
  evidence_count: number
}

export interface ArchitectureFinding {
  pattern: string
  name: string
  description: string
  confidence: string
  evidence_count: number
}

export interface StructureSummary {
  total_files: number
  inspected_files: number
  ignored_files: number
}

export interface RepositoryAnalysisResult {
  repository_id: number
  commit_sha: string
  analyzed_at: string
  scope: string
  time_range: Record<string, string | null> | null
  structure: StructureSummary
  languages: LanguageFinding[]
  frameworks: FrameworkFinding[]
  architecture: ArchitectureFinding[]
  evidence_count: number
  budget: {
    inspected_files?: number
    ignored_files?: number
    inspected_bytes?: number
    limits?: Record<string, number>
    [key: string]: unknown
  }
}

export interface EvidenceItem {
  repository_id: number
  commit_sha: string
  file_path: string
  finding_type: string
  classification: string
  evidence_source: string
  detection_method: string
  confidence: string
  confidence_score: number
  rationale: string
  line_number: number | null
  matched_content: string | null
  scope: string
  time_range: Record<string, string | null> | null
  timestamp: string
}

export interface EvidenceListResult {
  repository_id: number
  commit_sha: string
  total: number
  items: EvidenceItem[]
}

export interface AnalysisJobInfo {
  id: string
  repo_id: number
  scope: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'cancel_requested'
  progress: number
  step: string
  error_code: string | null
  retry_of: string | null
}

