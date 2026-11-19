import { useEffect, useState } from 'react'
import { getCurrentUser, logout } from '@/features/auth/api'
import { fetchRepositories, fetchSyncStatus, triggerSync } from '@/features/github/api'
import type { Repository, SyncStatusResponse } from '@/features/github/types'
import { apiFetch } from '@/shared/api/client'
import './pixel-studio.css'

type Skill = {
  id: number | null
  technology: string
  kind: 'language' | 'framework'
  status: string
  score: number | null
  rubric_version: string | null
  explanation?: string
}
type BackendState = 'loading' | 'authenticated' | 'unauthenticated' | 'error'
const links = [
  ['/dashboard', 'Dashboard API'],
  ['/role-scores', 'Role scoring'],
  ['/job-matching', 'Job matching'],
  ['/cv-studio', 'CV Studio'],
  ['/cvs', 'CV Workspace'],
  ['/mentor', 'AI Mentor'],
  ['/ai-audit', 'AI Audit'],
  ['/system-status', 'System status'],
] as const

export function PixelStudioPage() {
  const [auth, setAuth] = useState<BackendState>('loading')
  const [username, setUsername] = useState('')
  const [repositories, setRepositories] = useState<Repository[]>([])
  const [sync, setSync] = useState<SyncStatusResponse | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [reportId, setReportId] = useState('')
  const [rubric, setRubric] = useState('2.1.0')
  const [skills, setSkills] = useState<Skill[]>([])
  const [message, setMessage] = useState('')
  const [working, setWorking] = useState(false)
  const [drawer, setDrawer] = useState(true)

  async function refresh() {
    setMessage('')
    setAuth('loading')
    try {
      const user = await getCurrentUser()
      setUsername(user.full_name || user.email || 'GitHub user')
      setAuth('authenticated')
      const [repoResult, syncResult] = await Promise.all([
        fetchRepositories({ per_page: 100 }),
        fetchSyncStatus(),
      ])
      setRepositories(repoResult.items)
      setSync(syncResult)
      setSelected(previous => previous ?? repoResult.items[0]?.id ?? null)
    } catch (error) {
      const status = (error as { status?: number }).status
      setAuth(status === 401 ? 'unauthenticated' : 'error')
      setMessage(error instanceof Error ? error.message : 'Không thể kết nối backend')
    }
  }

  useEffect(() => {
  const controller = new AbortController()

  void Promise.resolve().then(() => {
    if (!controller.signal.aborted) {
      void refresh()
    }
  })

  return () => controller.abort()
}, [])

  async function loadScores() {
    if (!selected || !/^\\d+$/.test(reportId)) {
      setMessage('Chọn repository và nhập report ID thực tế từ trang Analysis.')
      return
    }
    setWorking(true)
    setMessage('')
    try {
      const query = new URLSearchParams({ report_id: reportId, rubric_version: rubric })
      const result = await apiFetch<Skill[]>(`/scoring/repositories/${selected}/skills?${query}`)
      setSkills(result)
      if (!result.length) setMessage('Chưa có snapshot cho report và rubric này.')
    } catch (error) {
      setSkills([])
      setMessage(error instanceof Error ? error.message : 'Không thể tải skill scores')
    } finally {
      setWorking(false)
    }
  }

  async function synchronize() {
    setWorking(true)
    setMessage('')
    try {
      const result = await triggerSync(true, 'public')
      setMessage(result.message || 'Đã gửi yêu cầu đồng bộ. Hãy tải lại sau khi worker hoàn thành.')
      setSync(await fetchSyncStatus())
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Đồng bộ thất bại')
    } finally {
      setWorking(false)
    }
  }

  async function signOut() {
    setWorking(true)
    try {
      await logout()
      setAuth('unauthenticated')
      setRepositories([])
      setSkills([])
      setSync(null)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Đăng xuất thất bại')
    } finally {
      setWorking(false)
    }
  }

  return <div className="pixel-integration">
    <header className="pixel-integration-header">
      <strong>IT Talent · Pixel Studio</strong>
      <span className="pixel-live-tag">Pixel Studio: visual demo · API panel: live backend</span>
      <button type="button" onClick={() => setDrawer(value => !value)}>{drawer ? 'Ẩn dữ liệu thật' : 'Hiện dữ liệu thật'}</button>
      <a href="/dashboard">Mở dashboard React</a>
    </header>
    <div className="pixel-integration-body">
      <iframe title="IT Talent Pixel Studio design" src="/pixel-studio/index.html#about" className="pixel-demo-frame"/>
      {drawer && <aside className="pixel-live-panel" aria-label="Backend data panel">
        <h2>Backend thật</h2>
        <p className="pixel-muted">Phần này đọc dữ liệu FastAPI; các số liệu mẫu bên trong Pixel Studio chưa được thay thế.</p>
        <p>Session: <b>{auth}</b> {auth === 'authenticated' ? `· ${username}` : ''}</p>
        {auth === 'unauthenticated' && <a className="pixel-primary" href="/api/v1/auth/github">Đăng nhập GitHub OAuth</a>}
        <div className="pixel-controls">
          <button onClick={() => void refresh()} disabled={working}>Tải lại dữ liệu</button>
          {auth === 'authenticated' && <button onClick={() => void signOut()} disabled={working}>Đăng xuất</button>}
        </div>
        {auth === 'authenticated' && <>
          <h3>GitHub repositories ({repositories.length})</h3>
          <p>Sync: {sync?.status ?? 'unknown'} · {sync?.is_connected ? 'Connected' : 'Not connected'}</p>
          <button disabled={working} onClick={() => void synchronize()}>Đồng bộ public repos</button>
          <label htmlFor="pixel-repo">Repository</label>
          <select id="pixel-repo" value={selected ?? ''} onChange={event => { setSelected(Number(event.target.value)); setSkills([]) }}>
            {repositories.map(repo => <option key={repo.id} value={repo.id}>{repo.full_name}{repo.private ? ' (private)' : ''}</option>)}
          </select>
          {selected !== null && <>
            <a href={`/repositories/${selected}/analysis`}>Phân tích repository trong React</a>
            <a href={`/repositories/${selected}/activity`}>GitHub activity thật</a>
            <h3>Verified skill snapshots</h3>
            <label htmlFor="pixel-report">Report ID</label>
            <input id="pixel-report" type="number" min="1" value={reportId} onChange={event => setReportId(event.target.value)} placeholder="Nhập ID báo cáo"/>
            <label htmlFor="pixel-rubric">Rubric</label>
            <select id="pixel-rubric" value={rubric} onChange={event => setRubric(event.target.value)}>
              <option value="2.1.0">2.1.0</option>
              <option value="2.0.0">2.0.0</option>
            </select>
            <button disabled={working} onClick={() => void loadScores()}>Tải điểm từ backend</button>
            <ul className="pixel-skill-list">
              {skills.map(skill => <li key={`${skill.kind}-${skill.technology}`}>
                <b>{skill.technology}</b> — {skill.score === null ? skill.status : `${skill.score}/100`}
                <small>{skill.kind} · {skill.rubric_version}</small>
              </li>)}
            </ul>
          </>}
        </>}
        {message && <p role="status" className="pixel-notice">{message}</p>}
        <h3>Chức năng backend đã có</h3>
        <nav className="pixel-api-links">
          {links.map(([href, title]) => <a href={href} key={href}>{title}</a>)}
        </nav>
      </aside>}
    </div>
  </div>
}
