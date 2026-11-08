import { apiFetch } from '@/shared/api/client'
import type { AuthUser } from './types'

/**
 * Lấy thông tin người dùng đang đăng nhập.
 * Backend trả về HTTP 401 nếu chưa đăng nhập.
 */
export function getCurrentUser(): Promise<AuthUser> {
  return apiFetch<AuthUser>('/auth/me')
}

/**
 * Đăng xuất và thu hồi session hiện tại.
 */
export function logout(): Promise<void> {
  return apiFetch<void>('/auth/logout', {
    method: 'POST',
  })
}