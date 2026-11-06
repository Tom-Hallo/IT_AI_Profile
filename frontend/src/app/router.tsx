import { createBrowserRouter } from 'react-router'
import { SystemStatusPage } from '@/features/system-status/SystemStatusPage'
import { NotFoundPage } from './NotFoundPage'

/** PBI-001 chỉ có một trang: kiểm tra hệ thống. Không có route nghiệp vụ. */
export const router = createBrowserRouter([
  { path: '/', element: <SystemStatusPage /> },
  { path: '*', element: <NotFoundPage /> },
])
