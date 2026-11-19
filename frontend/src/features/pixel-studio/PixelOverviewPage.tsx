import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { fetchRepositories, fetchSyncStatus, triggerSync } from '@/features/github/api'
import type { Repository, SyncStatusResponse } from '@/features/github/types'
import { apiFetch, isAbortError } from '@/shared/api/client'

interface RoleList { roles: { role_key: string; name: string }[] }
interface RoleScopeScore { public?: { score?: { status: string; role_score: number | null; confidence: number | null } | null }; rubric_version?: string }
type Phase = 'loading' | 'ready' | 'error'

export function PixelOverviewPage() {
  const { user, isLoading } = useAuth()
  const [phase, setPhase] = useState<Phase>('loading')
  const [repos, setRepos] = useState<Repository[]>([])
  const [sync, setSync] = useState<SyncStatusResponse | null>(null)
  const [role, setRole] = useState<{ name: string; score: number | null; status: string; version: string } | null>(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [syncing, setSyncing] = useState(false)

  useEffect(() => {
    if (!user) return
    const controller = new AbortController()
    void Promise.resolve().then(() => { if (!controller.signal.aborted) setPhase('loading') })
    void Promise.allSettled([
      fetchRepositories({ per_page: 100 }, controller.signal),
      fetchSyncStatus(controller.signal),
      apiFetch<RoleList>('/role-scoring/roles', { signal: controller.signal }),
    ]).then(async results => {
      if (controller.signal.aborted) return
      const [repositoriesResult, syncResult, rolesResult] = results
      if (repositoriesResult.status === 'fulfilled') setRepos(repositoriesResult.value.items)
      else setRepos([])
      if (syncResult.status === 'fulfilled') setSync(syncResult.value)
      else setSync(null)
      setRole(null)
      if (rolesResult.status === 'fulfilled' && rolesResult.value.roles.length) {
        const first = rolesResult.value.roles[0]
        try {
          const value = await apiFetch<RoleScopeScore>(`/role-scoring/roles/${encodeURIComponent(first.role_key)}/score/scoped`, { signal: controller.signal })
          if (!controller.signal.aborted) setRole({name:first.name, score:value.public?.score?.role_score ?? null,
            status:value.public?.score?.status ?? 'Insufficient',version:value.rubric_version ?? '—'})
        } catch (e) { if (!isAbortError(e) && !controller.signal.aborted) setRole(null) }
      }
      if (controller.signal.aborted) return
      setPhase(repositoriesResult.status === 'rejected' && syncResult.status === 'rejected' ? 'error' : 'ready')
      setError(repositoriesResult.status === 'rejected' && syncResult.status === 'rejected' ? 'Không tải được dữ liệu GitHub. Kiểm tra kết nối và quyền truy cập.' : '')
    })
    return () => controller.abort()
  }, [user, revision])

  async function synchronize() {
    setSyncing(true); setError('')
    try {
      await triggerSync(true, 'public')
      setRevision(v => v + 1)
    } catch (e) { setError(e instanceof Error ? e.message : 'Không thể đồng bộ GitHub') }
    finally { setSyncing(false) }
  }

  return <div className="pixel-overview">
    <div className="pixel-hero"><div><p className="pixel-eyebrow">YOUR DEVELOPER INTELLIGENCE</p>
      <h1>Build your future <em>in code.</em></h1>
      <p>Hồ sơ năng lực dựa trên bằng chứng GitHub đã xác minh. Không tự gán điểm khi thiếu dữ liệu.</p>
      <div className="pixel-hero-actions"><Link to="/repositories" className="pixel-primary">Explore repositories <span>↗</span></Link>
        <Link to="/roadmap" className="pixel-outline">Career roadmap →</Link></div></div>
      <div className="pixel-orbit" aria-hidden="true"><div className="pixel-orbit-ring"/><div className="pixel-orbit-core">✦</div></div>
    </div>
    {!isLoading && !user && <div className="pixel-notice">Bạn chưa đăng nhập. <a href="/api/v1/auth/github">Kết nối GitHub</a> để xem dữ liệu thật.</div>}
    {phase === 'loading' && <p role="status">Đang tải dữ liệu từ backend…</p>}
    {error && <p role="alert" className="pixel-notice">{error} <button type="button" onClick={() => setRevision(v => v + 1)}>Thử lại</button></p>}
    <div className="pixel-stat-grid">
      <article className="pixel-stat"><span>REPOSITORIES</span><strong>{user && phase === 'ready' ? repos.length : '—'}</strong><small>{sync?.is_connected ? 'GitHub đã kết nối' : 'Chưa có kết nối xác thực'}</small></article>
      <article className="pixel-stat"><span>ROLE SCORE</span><strong>{role?.score == null ? '—' : `${role.score.toFixed(1)}/100`}</strong><small>{role ? `${role.name} · ${role.status}` : 'Chưa đủ bằng chứng để tính điểm'}</small></article>
      <article className="pixel-stat"><span>RUBRIC VERSION</span><strong>{role?.version ?? '—'}</strong><small>Đọc trực tiếp từ scoring API</small></article>
      <article className="pixel-stat"><span>GITHUB SYNC</span><strong className="pixel-status-value">{sync?.status ?? '—'}</strong><small>{sync?.last_synced_at ? new Date(sync.last_synced_at).toLocaleString('vi-VN') : 'Chưa có lần đồng bộ'}</small></article>
    </div>
    <div className="pixel-overview-columns"><section className="pixel-panel"><div className="pixel-panel-heading"><div><p className="pixel-eyebrow">SOURCE OF TRUTH</p><h2>Repository explorer</h2></div>
      <button type="button" disabled={!user || syncing} onClick={() => void synchronize()}>{syncing ? 'Đang đồng bộ…' : '↻ Sync GitHub'}</button></div>
      {!repos.length ? <p className="pixel-empty">Chưa có repository đã đồng bộ. Kết nối GitHub và chạy Sync để bắt đầu.</p> :
      <div className="pixel-repo-list">{repos.slice(0,8).map(repo => <Link key={repo.id} to={`/repositories/${repo.id}/analysis`} className="pixel-repo-row"><span className="pixel-repo-glyph">⌘</span><span><strong>{repo.full_name}</strong><small>{repo.primary_language ?? 'Chưa xác định'} · {repo.private ? 'Private' : 'Public'}</small></span><span className="pixel-row-arrow">↗</span></Link>)}</div>}
      <Link className="pixel-panel-footer" to="/repositories">Open all repositories →</Link></section>
      <section className="pixel-panel"><p className="pixel-eyebrow">YOUR NEXT MOVES</p><h2>Growth workspace</h2>
      <div className="pixel-quick-links"><Link to="/role-scores"><span>◎</span><div><strong>Skill assessment</strong><small>Rubric và bằng chứng đã xác minh</small></div>↗</Link>
      <Link to="/roadmap"><span>◇</span><div><strong>Career roadmap</strong><small>Lộ trình và milestone thật</small></div>↗</Link>
      <Link to="/job-matching"><span>▤</span><div><strong>Job matching</strong><small>Đối chiếu JD với kỹ năng</small></div>↗</Link>
      <Link to="/cv-studio"><span>▧</span><div><strong>CV intelligence</strong><small>CV và ATS review</small></div>↗</Link>
      <Link to="/mentor"><span>✧</span><div><strong>AI Mentor</strong><small>Hỏi đáp qua API, không giả lập</small></div>↗</Link></div></section></div>
  </div>
}
