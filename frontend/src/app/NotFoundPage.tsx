import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <main className="status-page">
      <h1>Không tìm thấy trang</h1>
      <p>
        <Link to="/">Về trang kiểm tra hệ thống</Link>
      </p>
    </main>
  )
}
