import { apiFetch } from '@/shared/api/client'
import type { MentorChatRequest, MentorChatResponse, MentorSourceOptions } from './types'

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
