import type { ApiError } from '@/shared/api/client'

export interface ErrorDescription {
  title: string
  hint: string
}

/** Chuyển ApiError thành thông báo tiếng Việt dễ hiểu, không lộ nội dung thô từ server. */
export function describeError(error: ApiError): ErrorDescription {
  switch (error.kind) {
    case 'config':
      return {
        title: 'Thiếu hoặc sai cấu hình địa chỉ API',
        hint: 'Kiểm tra biến VITE_API_BASE_URL (mặc định /api/v1) rồi khởi động lại frontend.',
      }
    case 'timeout':
      return {
        title: 'Backend không phản hồi kịp thời',
        hint: 'Backend có thể đang khởi động hoặc quá tải. Thử lại sau vài giây.',
      }
    case 'network':
      return {
        title: 'Không kết nối được tới Backend',
        hint: 'Kiểm tra Backend đã chạy chưa (docker compose ps) và mạng của bạn.',
      }
    case 'invalid_response':
      return {
        title: 'Backend trả dữ liệu không đúng định dạng',
        hint: 'Có thể Backend và Frontend đang dùng hai phiên bản hợp đồng API khác nhau.',
      }
    case 'http': {
      const status = error.status
      // Proxy của Vite trả 502 (hoặc 504 khi quá hạn) lúc không chuyển được yêu cầu tới Backend.
      if (status === 502 || status === 504) {
        return {
          title: 'Không kết nối được tới Backend',
          hint: `Proxy không chuyển được yêu cầu tới Backend (HTTP ${status}). Kiểm tra Backend đã chạy chưa (docker compose ps, docker compose logs backend).`,
        }
      }
      return {
        title: `Backend trả lỗi HTTP ${status ?? '?'}`,
        hint: 'Backend đang chạy nhưng xử lý yêu cầu bị lỗi. Xem log của Backend (docker compose logs backend).',
      }
    }
  }
}
