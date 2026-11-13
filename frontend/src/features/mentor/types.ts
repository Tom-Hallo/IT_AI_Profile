export type SourceKey = 'github' | 'cv' | 'jd' | 'roadmap'

export type MentorSources = {
  github_repo_ids: number[]
  include_cv: boolean
  cv_ids: number[]
  jd_text: string | null
  roadmap_ids: number[]
}

export type MentorChatRequest = {
  message: string
  enable_actions?: boolean
  sources: MentorSources
}

export type MentorSourceOptions = {
  cvs: { id: number; uploaded_at: string }[]
  roadmaps: { id: number; title: string }[]
}

export type EvidenceRef = {
  id: string
  source: SourceKey
  label: string
  detail?: string | null
}

export type MentorLimitation = {
  code: string
  message: string
}

export type MentorChatResponse = {
  answer: string
  evidence: EvidenceRef[]
  limitations: MentorLimitation[]
  sources_used: SourceKey[]
  confidence: number | null
  provider_available: boolean
  action?: MentorAction | null
}

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  action?: MentorAction | null
  sourcesUsed?: SourceKey[]
  evidence?: EvidenceRef[]
  limitations?: MentorLimitation[]
  confidence?: number | null
}

export type MentorToolProposal =
  | { tool: 'create_cv'; title: string; summary: string; skills: string[] }
  | { tool: 'create_roadmap'; title: string; steps: string[] }
  | { tool: 'reanalyze_repository'; repository_id: number }

export type MentorAction = {
  id: string
  tool: MentorToolProposal['tool']
  sources: string[]
  impact: string
  proposal: MentorToolProposal
  expires_at: string
}

export type MentorActionDecision = 'confirm' | 'decline'
export type MentorActionResult = {
  status: 'pending' | 'declined' | 'expired' | 'succeeded' | 'denied' | 'failed'
  result_id: string | null
}
