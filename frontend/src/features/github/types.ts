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
  verification?: RepositoryVerificationResult | null
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

/**
 * Types for PBI-013 Fork, Ownership & Real Contribution Verification.
 */

export interface VerificationEvidenceItem {
  id?: number
  evidence_type: string
  target_identifier: string
  verification_status: 'verified' | 'unverified' | 'unknown'
  actor_login: string | null
  actor_id: string | null
  actor_type: string | null
  html_url: string | null
  title_or_message: string | null
  is_merge: boolean
  is_bot: boolean
  is_fork_inherited: boolean
  additions: number | null
  deletions: number | null
  pr_state: string | null
  pr_merged: boolean | null
  source_repo: string | null
  target_repo: string | null
  recorded_at: string | null
  rationale: string
  metadata?: Record<string, unknown> | null
}

export interface RepositoryVerificationResult {
  id?: number
  repository_id: number
  repository_name: string
  repository_full_name: string
  user_id: number
  job_id: string | null
  report_id: number | null
  provenance_type: 'original' | 'fork' | 'collaboration' | 'unknown'
  ownership_status: 'owner' | 'fork_owner' | 'collaborator' | 'unknown'
  is_fork: boolean
  parent_repo_name: string | null
  parent_repo_url: string | null
  parent_metadata_status: 'verified' | 'unknown' | 'inaccessible' | 'none'
  verification_status: 'verified' | 'unknown' | 'unverified' | 'no_contribution'
  coverage_status: 'complete' | 'partial' | 'unknown'
  confidence: 'high' | 'medium' | 'low' | 'uncertain'
  verified_commits_count: number
  unverified_commits_count: number
  verified_prs_count: number
  unverified_prs_count: number
  verified_additions: number
  verified_deletions: number
  anti_inflation_flag: boolean
  time_range: Record<string, string | null> | null
  limitations: string[]
  summary_data: Record<string, unknown>
  verified_at: string
  evidence: VerificationEvidenceItem[]
}

export interface VerificationEvidenceListResult {
  repository_id: number
  total: number
  page: number
  per_page: number
  items: VerificationEvidenceItem[]
}

/**
 * Types for PBI-014: Pull Request, Review, CI & Problem-Solving Analysis.
 */

export interface CollaborationEvidenceItem {
  id?: number
  evidence_type: string
  target_identifier: string
  pr_number?: number | null
  commit_sha?: string | null
  check_name?: string | null
  state?: string | null
  conclusion?: string | null
  actor_login?: string | null
  actor_id?: string | null
  actor_type?: string | null
  is_profile_owner: boolean
  html_url?: string | null
  title_or_message?: string | null
  recorded_at?: string | null
  rationale: string
  metadata?: Record<string, unknown> | null
}

export interface CollaborationObservation {
  category: 'pull_request' | 'review' | 'ci_check' | 'problem_solving' | string
  title: string
  description: string
  evidence_level: 'observed_event' | 'evidence_backed_relationship' | 'contextual_explanation' | string
  confidence: 'high' | 'medium' | 'uncertain' | string
  related_identifiers: string[]
}

export interface ProblemSolvingSequence {
  sequence_id: string
  pr_number?: number | null
  trigger_event: Record<string, unknown>
  iteration_events: Record<string, unknown>[]
  resolution_or_outcome: Record<string, unknown>
  cycle_duration_seconds?: number | null
  explanation: string
  limitations: string[]
}

export interface RepositoryCollaborationResult {
  id?: number
  repository_id: number
  repository_name: string
  repository_full_name: string
  user_id: number
  job_id: string | null
  report_id: number | null
  total_prs_analyzed: number
  merged_prs_count: number
  closed_unmerged_prs_count: number
  open_prs_count: number
  user_prs_count: number
  external_prs_count: number
  total_reviews_analyzed: number
  approved_reviews_count: number
  changes_requested_count: number
  commented_reviews_count: number
  dismissed_reviews_count: number
  user_reviews_conducted_count: number
  user_reviews_received_count: number
  total_checks_analyzed: number
  successful_checks_count: number
  failed_checks_count: number
  pending_checks_count: number
  other_checks_count: number
  problem_solving_sequences_count: number
  coverage_status: 'complete' | 'partial' | 'insufficient'
  confidence: 'high' | 'medium' | 'uncertain'
  time_range: Record<string, string | null> | null
  limitations: string[]
  collaboration_observations: CollaborationObservation[]
  problem_solving_sequences: ProblemSolvingSequence[]
  summary_data: Record<string, unknown>
  analyzed_at: string
  evidence: CollaborationEvidenceItem[]
}

export interface CollaborationEvidenceListResult {
  repository_id: number
  total: number
  page: number
  per_page: number
  items: CollaborationEvidenceItem[]
}

