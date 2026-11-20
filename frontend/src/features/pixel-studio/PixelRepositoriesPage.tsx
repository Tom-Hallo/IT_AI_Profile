import { Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { GitHubRepositoriesSection } from '@/features/github/GitHubRepositoriesSection'

export function PixelRepositoriesPage() {
  const { user } = useAuth()
  return (
    <div>
      <div className="pixel-page-heading">
        <p className="pixel-eyebrow">GITHUB / LIVE API</p>
        <h1>GitHub repositories</h1>
        <p>Danh sách, đồng bộ và quyền riêng tư lấy từ FastAPI. Chỉ repo public được hiển thị khi chưa cấp quyền private.</p>
      </div>
      <div className="pixel-content-panel">
        {!user ? (
          <p className="pixel-empty">Đăng nhập bằng GitHub để xem và đồng bộ repositories của bạn.</p>
        ) : (
          <GitHubRepositoriesSection isAuthenticated={Boolean(user)} />
        )}
      </div>
      <div className="pixel-panel" style={{ padding: '18px 25px', marginTop: 16 }}>
        <div className="pixel-quick-links">
          <Link to="/dashboard"><span>▦</span><div><strong>Evidence dashboard</strong><small>Xem điểm theo scope và repository</small></div>↗</Link>
          <Link to="/role-scores"><span>◎</span><div><strong>Skill assessment</strong><small>Rubric và bằng chứng đã xác minh</small></div>↗</Link>
          <Link to="/analysis"><span>⬡</span><div><strong>Phân tích repository</strong><small>Code, kiến trúc và báo cáo AI</small></div>↗</Link>
        </div>
      </div>
    </div>
  )
}
