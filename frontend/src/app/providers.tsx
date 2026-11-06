import type { ReactNode } from 'react'

/**
 * Nơi gắn các provider dùng chung cho toàn ứng dụng.
 * PBI-001 chưa cần provider nào (chưa có state toàn cục, chưa có data-fetching library),
 * nên hiện chỉ trả về children. Các PBI sau thêm provider tại đây.
 */
export function AppProviders({ children }: { children: ReactNode }) {
  return <>{children}</>
}
