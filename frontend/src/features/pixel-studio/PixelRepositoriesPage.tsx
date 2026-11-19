import { Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { GitHubRepositoriesSection } from '@/features/github/GitHubRepositoriesSection'
export function PixelRepositoriesPage() { const { user } = useAuth(); return <section><p className="pixel-eyebrow">GITHUB / LIVE API</p><h1>GitHub repositories</h1><p>Danh sách, đồng bộ và quyền riêng tư lấy từ FastAPI.</p><GitHubRepositoriesSection isAuthenticated={Boolean(user)} /><p><Link to="/dashboard">Mở Evidence Dashboard →</Link></p></section> }
