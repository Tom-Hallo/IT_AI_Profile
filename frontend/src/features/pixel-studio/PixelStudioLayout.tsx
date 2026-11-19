import { useState } from 'react'
import { NavLink, Outlet, Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import './pixel-studio.css'

const navigation = [
  { to: '/', label: 'Overview', icon: '◈', end: true },
  { to: '/dashboard', label: 'Evidence dashboard', icon: '▦' },
  { to: '/repositories', label: 'GitHub repositories', icon: '⌘' },
  { to: '/role-scores', label: 'Skill assessment', icon: '◎' },
  { to: '/roadmap', label: 'Career roadmap', icon: '◇' },
  { to: '/job-matching', label: 'Job matching', icon: '▤' },
  { to: '/cv-studio', label: 'CV intelligence', icon: '▧' },
  { to: '/mentor', label: 'AI mentor', icon: '✧' },
  { to: '/privacy', label: 'Privacy & consent', icon: '⬡' },
  { to: '/system-status', label: 'System status', icon: '◉' },
]

export function PixelStudioLayout() {
  const { user, isLoading } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  return <div className="pixel-app">
    <aside className={`pixel-sidebar ${menuOpen ? 'pixel-sidebar-open' : ''}`}>
      <Link to="/" className="pixel-brand" onClick={() => setMenuOpen(false)}>
        <span className="pixel-brand-symbol">✦</span><span><strong>IT TALENT</strong><small>PIXEL STUDIO</small></span>
      </Link>
      <p className="pixel-sidebar-heading">WORKSPACE</p>
      <nav aria-label="Điều hướng chính" className="pixel-navigation">
        {navigation.map(item => <NavLink key={item.to} to={item.to} end={item.end}
          onClick={() => setMenuOpen(false)} className={({isActive}) => `pixel-nav-item ${isActive ? 'pixel-nav-active' : ''}`}>
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
        <span className="pixel-breadcrumb">Developer workspace <span>/</span> Evidence-based profile</span>
        <div className="pixel-topbar-actions"><span className="pixel-api-indicator"><span className="pixel-status-dot"/> LIVE API</span>
          <Link to="/mentor" className="pixel-topbar-chat">✧ Ask AI Mentor</Link></div>
      </header>
      <main id="pixel-main" className="pixel-main"><Outlet /></main>
    </div>
    {menuOpen && <button className="pixel-mobile-backdrop" aria-label="Đóng menu" onClick={() => setMenuOpen(false)} />}
  </div>
}
