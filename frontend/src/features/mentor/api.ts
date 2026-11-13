import { apiFetch } from '@/shared/api/client'
import type { MentorActionDecision, MentorActionResult, MentorChatRequest, MentorChatResponse, MentorSourceOptions } from './types'

export function sendMentorChat(
  payload: MentorChatRequest,
  signal?: AbortSignal,
): Promise<MentorChatResponse> {
  return apiFetch<MentorChatResponse>('/mentor/chat', {
    method: 'POST',
    body: payload,
    signal,
    timeoutMs: 130_000,
  })
}

export function fetchMentorSources(signal: AbortSignal): Promise<MentorSourceOptions> {
  return apiFetch<MentorSourceOptions>('/mentor/sources', { signal })
}

export function decideMentorAction(id: string, decision: MentorActionDecision) {
  const operation = decision === 'confirm' ? 'approve' : 'decline'
  return apiFetch<MentorActionResult>(`/agent/actions/${encodeURIComponent(id)}/${operation}`, {
    method: 'POST',
  })
}
