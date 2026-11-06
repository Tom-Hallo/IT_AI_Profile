import { env } from '@/shared/config/env'

/** Phân loại lỗi để giao diện hiển thị thông báo phù hợp. */
export type ApiErrorKind =
  | 'config' // thiếu hoặc sai VITE_API_BASE_URL
  | 'timeout' // quá thời gian chờ
  | 'network' // không kết nối được (mất mạng, server tắt, bị chặn)
  | 'http' // server trả mã lỗi HTTP
  | 'invalid_response' // trả 2xx nhưng nội dung không đọc được

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | undefined
  /** Nội dung JSON của phản hồi lỗi (nếu có). Chỉ để xử lý logic, không hiển thị nguyên văn. */
  readonly body: unknown

  constructor(
    kind: ApiErrorKind,
    message: string,
    details: { status?: number; body?: unknown; cause?: unknown } = {},
  ) {
    super(message, { cause: details.cause })
    this.name = 'ApiError'
    this.kind = kind
    this.status = details.status
    this.body = details.body
  }
}

export interface ApiRequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  /** Được serialize thành JSON. */
  body?: unknown
  headers?: Record<string, string>
  /** Cho phép hủy từ bên ngoài (ví dụ khi component bị gỡ). */
  signal?: AbortSignal
  timeoutMs?: number
}

/** Backend được yêu cầu trả health trong dưới 5 giây kể cả khi dependency hỏng (Blueprint mục 7.1). */
export const DEFAULT_TIMEOUT_MS = 8000

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  return new ApiError('network', 'Không thể kết nối tới Backend', { cause: error })
}

function buildUrl(baseUrl: string, path: string): string {
  if (!path.startsWith('/')) {
    throw new ApiError('config', `Đường dẫn API phải bắt đầu bằng "/": ${path}`)
  }
  return `${baseUrl}${path}`
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

/**
 * Gọi API của Backend. Mọi lời gọi từ frontend đều đi qua hàm này.
 * - Base URL lấy từ VITE_API_BASE_URL (mặc định theo Blueprint: `/api/v1`).
 * - Luôn ném `ApiError` (trừ khi bị hủy từ bên ngoài, khi đó ném `AbortError`).
 * - Không đưa nội dung phản hồi thô của server vào thông báo lỗi.
 */
export async function apiFetch<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  if (env.apiBaseUrl === null) {
    throw new ApiError('config', 'Thiếu hoặc sai cấu hình VITE_API_BASE_URL')
  }
  const url = buildUrl(env.apiBaseUrl, path)
  const { method = 'GET', body, headers, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options

  const timeoutSignal = AbortSignal.timeout(timeoutMs)
  const combinedSignal = signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal

  let response: Response
  try {
    response = await fetch(url, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      credentials: 'same-origin',
      signal: combinedSignal,
    })
  } catch (error) {
    if (signal?.aborted) throw error // bị hủy chủ động, để nơi gọi tự bỏ qua
    if (timeoutSignal.aborted) {
      throw new ApiError('timeout', 'Backend không phản hồi kịp thời', { cause: error })
    }
    throw new ApiError('network', 'Không thể kết nối tới Backend', { cause: error })
  }

  let payload: unknown
  try {
    payload = await readJson(response)
  } catch (error) {
    if (signal?.aborted) throw error
    if (timeoutSignal.aborted) {
      throw new ApiError('timeout', 'Backend không phản hồi kịp thời', { cause: error })
    }
    throw new ApiError('network', 'Mất kết nối khi đang nhận dữ liệu', { cause: error })
  }

  if (!response.ok) {
    throw new ApiError('http', `Backend trả lỗi HTTP ${response.status}`, {
      status: response.status,
      body: payload,
    })
  }
  if (response.status === 204) return undefined as T
  if (payload === undefined) {
    throw new ApiError('invalid_response', 'Phản hồi của Backend không phải JSON hợp lệ', {
      status: response.status,
    })
  }
  return payload as T
}
