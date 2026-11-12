import { apiFetch } from '@/shared/api/client'
import type { MentorChatRequest, MentorChatResponse } from './types'

export function sendMentorChat(
  payload: MentorChatRequest,
  signal?: AbortSignal,
): Promise<MentorChatResponse> {
  return apiFetch<MentorChatResponse>('/mentor/chat', {
    method: 'POST',
    body: payload,
    signal,
    timeoutMs: 120_000,
  })
}