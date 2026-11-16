import { useAuth } from '@/features/auth/useAuth'
import { GitHubRepositoriesSection } from '@/features/github/GitHubRepositoriesSection'
import { TalentOSLayout } from './TalentOSLayout'

export function GitHubRepositoriesPage() {
  const { user, isLoading, error } = useAuth()
  return <TalentOSLayout title="GitHub Repositories">
    <section className="talent-os__intro"><p className="talent-os__eyebrow">SOURCE INTELLIGENCE / LIVE DATA</p><h1>GitHub <span>Repositories.</span></h1><p>Đồng bộ repository, xem bằng chứng và phân tích mã nguồn trực tiếp từ FastAPI.</p></section>
    {isLoading ? <p role="status">Đang kiểm tra đăng nhập...</p> : error ? <p role="alert">{error}</p> : user ? <GitHubRepositoriesSection isAuthenticated={true} /> : <section className="talent-os__notice"><h2>Chưa đăng nhập</h2><p>Đăng nhập bằng GitHub để xem repository thật của bạn.</p></section>}
  </TalentOSLayout>
}
