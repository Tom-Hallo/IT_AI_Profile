export type SourceKey = 'github' | 'cv' | 'jd' | 'roadmap'

export type MentorSources = {
  github_repo_ids: number[]
  include_cv: boolean
  jd_text: string | null
  roadmap_ids: number[]
}

export type MentorChatRequest = {
  message: string
  sources: MentorSources
}

export type EvidenceRef = {
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
}

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  evidence?: EvidenceRef[]
  limitations?: MentorLimitation[]
  confidence?: number | null
}