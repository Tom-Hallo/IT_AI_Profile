import { ApiError, apiFetch } from '@/shared/api/client'

/**
 * Hợp đồng GET /api/v1/health theo Technical Blueprint mục 7.1.
 * 200 => status "ok"; 503 => status "degraded" (kèm checks cho biết dependency nào hỏng).
 */
export type CheckResult = 'ok' | 'fail'

export interface HealthResponse {
  status: 'ok' | 'degraded'
  service: string
  version: string
  checks: Record<string, CheckResult>
}

export function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  if (v.status !== 'ok' && v.status !== 'degraded') return false
  if (typeof v.service !== 'string' || typeof v.version !== 'string') return false
  if (typeof v.checks !== 'object' || v.checks === null) return false
  return Object.values(v.checks).every((c) => c === 'ok' || c === 'fail')
}

/**
 * Gọi endpoint health của Backend (không tự tạo endpoint nào khác).
 * - 200 hợp lệ => trả dữ liệu.
 * - 503 có body đúng khuôn "degraded" => trả dữ liệu (Backend sống nhưng dependency lỗi).
 * - Các trường hợp còn lại => ném ApiError.
 */
export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  try {
    const data = await apiFetch<unknown>('/health', { signal })
    if (!isHealthResponse(data)) {
      throw new ApiError('invalid_response', 'Backend trả dữ liệu không đúng định dạng health')
    }
    return data
  } catch (error) {
    if (error instanceof ApiError && error.kind === 'http' && error.status === 503) {
      if (isHealthResponse(error.body)) return error.body
    }
    throw error
  }
}
