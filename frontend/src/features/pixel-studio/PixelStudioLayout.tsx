import { useState, useEffect } from 'react'
import { NavLink, Outlet, Link, useSearchParams, useLocation } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { GitHubLogin } from '@/features/auth/GitHubLogin'
import './pixel-studio.css'

const navigation = [
  { to: '/', label: 'Overview', icon: '◈', end: true },
  { to: '/dashboard', label: 'Evidence dashboard', icon: '▦' },
  { to: '/repositories', label: 'GitHub repositories', icon: '⌘' },
  { to: '/role-scores', label: 'Skill assessment', icon: '◎' },
  { to: '/roadmap', label: 'Career roadmap', icon: '◇' },
  { to: '/job-matching', label: 'Job matching', icon: '▤' },
  { to: '/cvs', label: 'CV đã tải lên', icon: '▧' },
  { to: '/cv-studio', label: 'CV intelligence', icon: '▧' },
  { to: '/mentor', label: 'AI mentor', icon: '✧' },
  { to: '/privacy', label: 'Privacy & consent', icon: '⬡' },
  { to: '/profile-sharing', label: 'Chia sẻ hồ sơ', icon: '↗' },
  { to: '/ats-review', label: 'Phản hồi ATS', icon: '✓' },
  { to: '/ai-audit', label: 'Lịch sử sử dụng AI', icon: '≡' },
  { to: '/system-status', label: 'System status', icon: '◉' },
]

const pageNames: Record<string, string> = {
  '/': 'Overview', '/dashboard': 'Evidence dashboard',
  '/repositories': 'GitHub repositories', '/role-scores': 'Skill assessment',
  '/roadmap': 'Career roadmap', '/job-matching': 'Job matching',
  '/cvs': 'CV đã tải lên', '/cv-studio': 'CV intelligence',
  '/mentor': 'AI mentor', '/privacy': 'Privacy & consent',
  '/profile-sharing': 'Chia sẻ hồ sơ', '/ats-review': 'Phản hồi ATS',
  '/ai-audit': 'Lịch sử AI', '/system-status': 'System status',
}

export function PixelStudioLayout() {
  const { user, isLoading, isLoggingOut, error, signOut } = useAuth()
  const [params] = useSearchParams()
  const callbackError = params.get('auth_error')
  const [menuOpen, setMenuOpen] = useState(false)
  const [isDark, setIsDark] = useState(() => { try { return localStorage.getItem('pixel-theme') !== 'light' } catch { return true } })
  const location = useLocation()
  const pageName = pageNames[location.pathname] ?? pageNames[Object.keys(pageNames).find(k => k !== '/' && location.pathname.startsWith(k)) ?? ''] ?? 'IT Talent'

  function toggleTheme() {
    setIsDark(v => {
      const next = !v
      try { localStorage.setItem('pixel-theme', next ? 'dark' : 'light') } catch { /* ignore storage errors */ }
      document.documentElement.setAttribute('data-pixel-theme', next ? 'dark' : 'light')
      return next
    })
  }

  useEffect(() => {
    document.documentElement.setAttribute('data-pixel-theme', isDark ? 'dark' : 'light')
  }, [isDark])
  return <div className="pixel-app">
    <aside className={`pixel-sidebar ${menuOpen ? 'pixel-sidebar-open' : ''}`}>
      <Link to="/" className="pixel-brand" onClick={() => setMenuOpen(false)}>
        <span className="pixel-brand-symbol">✦</span><span><strong>IT TALENT</strong><small>PIXEL STUDIO</small></span>
      </Link>
      <p className="pixel-sidebar-heading">WORKSPACE</p>
      <nav aria-label="Điều hướng chính" className="pixel-navigation">
        {navigation.map(item => <NavLink key={item.to} to={item.to} end={item.end}
          onClick={() => setMenuOpen(false)} className={({ isActive }) => `pixel-nav-item ${isActive ? 'pixel-nav-active' : ''}`}>
          <span aria-hidden="true" className="pixel-nav-icon">{item.icon}</span>{item.label}
        </NavLink>)}
      </nav>
      <div className="pixel-sidebar-bottom"><span className="pixel-status-dot" />
        {isLoading ? 'Đang xác thực…' : user ? user.full_name || user.email : 'Chưa đăng nhập'}
      </div>
    </aside>
    <div className="pixel-workspace">
      <header className="pixel-topbar">
        <button type="button" className="pixel-menu-toggle" onClick={() => setMenuOpen(value => !value)} aria-label="Bật/tắt menu">☰</button>
        <span className="pixel-breadcrumb"><span className="pixel-breadcrumb-page">{pageName}</span></span>
        <div className="pixel-topbar-actions">
          <button type="button" className="pixel-topbar-theme" onClick={toggleTheme} aria-label="Đổi giao diện">{isDark ? '☀' : '☾'}</button>
          {user ? <button type="button" className="pixel-outline" disabled={isLoggingOut} onClick={() => void signOut()}>Đăng xuất</button>
            : !isLoading && <GitHubLogin />}
        </div>
      </header>
      <div id="pixel-main" className="pixel-main">
        {error && <p role="alert" className="pixel-notice">{error}</p>}
        {callbackError && <p role="alert" className="pixel-notice">
          {callbackError === 'github_access_denied' ? 'Bạn đã từ chối cấp quyền trên GitHub.'
            : callbackError === 'oauth_state_invalid' ? 'Phiên đăng nhập GitHub đã hết hạn. Hãy thử lại.'
              : callbackError === 'github_account_conflict' ? 'Tài khoản GitHub này đã liên kết với một hồ sơ khác.'
                : 'GitHub không thể hoàn tất đăng nhập. Hãy thử lại.'}
        </p>}
        <Outlet />
      </div>
    </div>
    {menuOpen && <button className="pixel-mobile-backdrop" aria-label="Đóng menu" onClick={() => setMenuOpen(false)} />}
  </div>
}
