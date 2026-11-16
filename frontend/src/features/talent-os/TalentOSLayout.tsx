import { useState, type ReactNode } from 'react'
import { Link, NavLink } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { env } from '@/shared/config/env'
import { MentorPage } from '@/features/mentor/MentorPage'
import './TalentOSLayout.css'

const navigation = [
  { to: '/talent-os', icon: '◈', title: 'Dashboard', end: true },
  { to: '/talent-os/github', icon: '⌘', title: 'GitHub Repositories', end: false },
  { to: '/role-scores', icon: '◇', title: 'Role Scoring', end: false },
  { to: '/analysis', icon: '⬡', title: 'Analysis & Evidence', end: false },
  { to: '/activity', icon: '◎', title: 'Activity', end: false },
  { to: '/talent-os/roadmap', icon: '▤', title: 'Roadmap Tracking', end: false },
  { to: '/talent-os/history', icon: '◷', title: 'Score History', end: false },
  { to: '/talent-os/privacy', icon: '♢', title: 'Privacy & Consent', end: false },
]

export function TalentOSLayout({ children, title }: { children: ReactNode; title: string }) {
  const { user, isLoading, signOut } = useAuth()
  const [chatOpen, setChatOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [dark, setDark] = useState(() => {
    try { return localStorage.getItem('talent-os-theme') !== 'light' } catch { return true }
  })
  const [chatWidth, setChatWidth] = useState(400)

  function toggleTheme() {
    setDark(previous => {
      try { localStorage.setItem('talent-os-theme', previous ? 'light' : 'dark') } catch { /* storage may be disabled */ }
      return !previous
    })
  }

  function startResize(event: React.PointerEvent<HTMLDivElement>) {
    if (window.innerWidth < 900) return
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  function resize(event: React.PointerEvent<HTMLDivElement>) {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return
    setChatWidth(Math.max(320, Math.min(700, window.innerWidth - event.clientX)))
  }

  return (
    <div className={`talent-os ${dark ? 'talent-os--dark' : 'talent-os--light'} ${chatOpen ? 'talent-os--chat' : ''}`} style={{ '--talent-chat-width': `${chatWidth}px` } as React.CSSProperties}>
      <div className="talent-os__code" aria-hidden="true"><span>const talent = await analyze(github.repositories)</span><span>from fastapi import APIRouter</span><span>SELECT skills FROM evidence WHERE verified = true;</span><span>function buildFuture() {'{'} return growth; {'}'}</span></div>
      {!chatOpen && <aside className={`talent-os__sidebar ${menuOpen ? 'talent-os__sidebar--open' : ''}`}>
        <Link className="talent-os__brand" to="/talent-os"><span className="talent-os__brand-icon">✦</span><span><strong>IT TALENT</strong><small>AI PROFILE / OS</small></span></Link>
        <p className="talent-os__nav-label">WORKSPACE</p>
        <nav aria-label="Talent OS navigation">{navigation.map(item => <NavLink key={item.to} end={item.end} to={item.to} onClick={() => setMenuOpen(false)} className={({ isActive }) => `talent-os__nav-link ${isActive ? 'talent-os__nav-link--active' : ''}`}><span>{item.icon}</span>{item.title}</NavLink>)}</nav>
        <div className="talent-os__sidebar-footer"><span className="talent-os__online">●</span> {isLoading ? 'Checking session' : user ? user.full_name : 'Guest workspace'}
          {user ? <button type="button" onClick={() => void signOut()}>Đăng xuất</button> : env.apiBaseUrl ? <a href={`${env.apiBaseUrl}/auth/github`}>Đăng nhập GitHub</a> : <small>Chưa cấu hình API URL</small>}
        </div>
      </aside>}
      <div className="talent-os__shell">
        <header className="talent-os__topbar"><button type="button" className="talent-os__mobile-menu" onClick={() => setMenuOpen(v => !v)} aria-label="Mở menu">☰</button><span>WORKSPACE <b>/ {title}</b></span><div className="talent-os__top-actions"><span className="talent-os__system">● LIVE BACKEND</span><button type="button" onClick={toggleTheme} aria-label="Đổi giao diện sáng tối">{dark ? '☀' : '☾'}</button><span className="talent-os__avatar">{user?.full_name?.slice(0, 2).toUpperCase() ?? 'DV'}</span></div></header>
        <div className="talent-os__workspace"><main className="talent-os__content" id="talent-os-main">{children}</main>{chatOpen && <aside className="talent-os__chat" aria-label="AI Mentor"><div className="talent-os__resize" role="separator" tabIndex={0} aria-label="Thay đổi chiều rộng chat" onPointerDown={startResize} onPointerMove={resize} onKeyDown={e => { if (e.key === 'ArrowLeft') setChatWidth(w => Math.min(700, w + 20)); if (e.key === 'ArrowRight') setChatWidth(w => Math.max(320, w - 20)) }} /><div className="talent-os__chat-header"><strong>✦ Talent Copilot</strong><button type="button" onClick={() => setChatOpen(false)} aria-label="Đóng chat">×</button></div><div className="talent-os__chat-body"><MentorPage /></div></aside>}</div>
      </div>
      {!chatOpen && <button className="talent-os__glic" type="button" onClick={() => setChatOpen(true)} aria-label="Mở AI Mentor">✦</button>}
    </div>
  )
}
