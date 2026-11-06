/**
 * Đọc cấu hình từ biến môi trường của Vite.
 * Quy tắc (Blueprint mục 5): chỉ biến VITE_* được lộ ra trình duyệt, không đặt secret.
 */

/**
 * Chuẩn hóa API base URL.
 * Chấp nhận đường dẫn tương đối (`/api/v1`, mặc định theo Blueprint) hoặc URL tuyệt đối http(s).
 * Trả về `null` nếu thiếu hoặc sai định dạng để lớp gọi API báo lỗi cấu hình rõ ràng.
 */
export function normalizeApiBaseUrl(value: string | undefined): string | null {
  const trimmed = value?.trim()
  if (!trimmed) return null
  const isRelative = trimmed.startsWith('/') && !trimmed.startsWith('//')
  const isAbsolute = /^https?:\/\/[^\s/]+/i.test(trimmed)
  if (!isRelative && !isAbsolute) return null
  return trimmed.replace(/\/+$/, '')
}

export const env = {
  /** `null` nghĩa là thiếu hoặc sai VITE_API_BASE_URL. */
  apiBaseUrl: normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL),
} as const
