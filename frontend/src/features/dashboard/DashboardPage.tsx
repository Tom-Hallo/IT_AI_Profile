import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import type { AuthUser } from '@/features/auth/types'
import type { RepositoryListResponse } from '@/features/github/types'
import { Card } from '@/shared/ui/Card'
import { DashboardEvidence } from './DashboardEvidence'
import { ProfileSummary } from './ProfileSummary'
import { useDashboardQuery } from './useDashboardQuery'
import './DashboardPage.css'

type Scope = 'public' | 'private' | 'combined'
type RoleSummary = { role_key: string; name: string }
type Limitation = { code: string; message: string }
type ScopedResult = Record<Scope, {
  score: {
    status: string
    role_score: number | null
    confidence: number | null
    coverage: number
    rationale: string
    limitations: Limitation[]
  } | null
  limitations: Limitation[]
}> & { rubric_version: string }

const scopes: { key: Scope; label: string }[] = [
  { key: 'public', label: 'Công khai' },
  { key: 'private', label: 'Riêng tư' },
  { key: 'combined', label: 'Kết hợp' },
]

function Metric({ label, value }: { label: string; value: number | null }) {
  return <div className="dashboard-metric">
    <span>{label}</span>
    {value === null ? <strong>Chưa đủ bằng chứng</strong> : <>
      <strong>{value.toFixed(1)}/100</strong>
      <meter min={0} max={100} value={value} aria-label={label} />
    </>}
  </div>
}

function RoleScore({ role, scope, dates }: { role: string; scope: Scope; dates: string }) {
  const { state, retry } = useDashboardQuery<ScopedResult>(
    `/role-scoring/roles/${encodeURIComponent(role)}/score/scoped?${dates}`,
  )
  if (state.phase === 'loading') return <p role="status">Đang tính điểm…</p>
  if (state.phase === 'error') return <p role="alert">
    Không tải được điểm vai trò. <button type="button" onClick={retry}>Thử lại</button>
  </p>
  const current = state.data[scope]
  const score = current.score
  const limitations = [...new Set([
    ...current.limitations, ...(score?.limitations ?? []),
  ].map((item) => item.message))]
  return <Card>
    <div className="dashboard-metrics">
      <Metric label="Điểm vai trò" value={score?.role_score ?? null} />
      <Metric label="Confidence" value={score?.confidence ?? null} />
      <Metric label="Độ phủ tiêu chí" value={score ? score.coverage * 100 : null} />
    </div>
    <p>Rubric {state.data.rubric_version}{score ? ` · ${score.status}` : ''}</p>
    {score?.rationale && <p>{score.rationale}</p>}
    {limitations.length > 0 && <ul className="limitations">
      {limitations.map((message) => <li key={message}>{message}</li>)}
    </ul>}
  </Card>
}

function RolePanel({ scope, dates }: { scope: Scope; dates: string }) {
  const { state, retry } = useDashboardQuery<{ roles: RoleSummary[] }>('/role-scoring/roles')
  const [role, setRole] = useState('')
  if (state.phase === 'loading') return <p role="status">Đang tải vai trò…</p>
  if (state.phase === 'error') return <p role="alert">
    Không tải được vai trò. <button type="button" onClick={retry}>Thử lại</button>
  </p>
  const selected = role || state.data.roles[0]?.role_key
  if (!selected) return <p>Chưa có rubric vai trò.</p>
  return <>
    <p><label htmlFor="dashboard-role">Vai trò</label>{' '}
      <select id="dashboard-role" value={selected} onChange={(event) => setRole(event.target.value)}>
        {state.data.roles.map((item) => <option key={item.role_key} value={item.role_key}>{item.name}</option>)}
      </select>
    </p>
    <RoleScore key={`${selected}:${scope}:${dates}`} role={selected} scope={scope} dates={dates} />
  </>
}

function RepoPanel({ scope, dates }: { scope: Scope; dates: string }) {
  const [page, setPage] = useState(1)
  const [repoId, setRepoId] = useState('')
  const visibility = scope === 'combined' ? 'all' : scope
  const { state, retry } = useDashboardQuery<RepositoryListResponse>(
    `/github/repositories?visibility=${visibility}&per_page=50&page=${page}`,
  )
  if (state.phase === 'loading') return <p role="status">Đang tải repository…</p>
  if (state.phase === 'error') return <p role="alert">
    Không tải được repository. <button type="button" onClick={retry}>Thử lại</button>
  </p>
  const data = state.data
  const selected = data.items.find((repo) => String(repo.id) === repoId) ?? data.items[0]
  function changePage(next: number) {
    setPage(next)
    setRepoId('')
  }
  return <>
    {selected ? <>
      <p><label htmlFor="dashboard-repo">Repository</label>{' '}
        <select id="dashboard-repo" value={selected.id} onChange={(event) => setRepoId(event.target.value)}>
          {data.items.map((repo) => <option key={repo.id} value={repo.id}>{repo.full_name || repo.name}</option>)}
        </select>
      </p>
      <DashboardEvidence key={`${selected.id}:${dates}`} repoId={selected.id} dates={dates} />
    </> : <p>Chưa có repository trong phạm vi này.</p>}
    {data.total_pages > 1 && <nav className="dashboard-actions" aria-label="Trang repository">
      <button type="button" disabled={page <= 1} onClick={() => changePage(page - 1)}>Trang trước</button>
      <span>{page}/{data.total_pages}</span>
      <button type="button" disabled={page >= data.total_pages} onClick={() => changePage(page + 1)}>Trang sau</button>
    </nav>}
  </>
}

function DashboardContent({ user }: { user: AuthUser }) {
  const [scope, setScope] = useState<Scope>('public')
  const [dates, setDates] = useState('')
  const [dateError, setDateError] = useState('')
  function applyDates(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const start = String(fields.get('date_from') ?? '')
    const end = String(fields.get('date_to') ?? '')
    if (start && end && start > end) {
      setDateError('Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.')
      return
    }
    setDateError('')
    const query = new URLSearchParams()
    if (start) query.set('date_from', start)
    if (end) query.set('date_to', end)
    setDates(query.toString())
  }
  return <>
    <ProfileSummary user={user} />
    <Card className="dashboard-filters">
      <form className="filter-row" onSubmit={applyDates} onReset={() => {
        setDates('')
        setDateError('')
      }}>
        <div className="dashboard-scope-control">
          <label htmlFor="dashboard-scope">Phạm vi</label>
          <select id="dashboard-scope" value={scope} onChange={(event) => setScope(event.target.value as Scope)}>
            {scopes.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
          </select>
        </div>
        <label>Từ ngày (UTC)<input type="date" name="date_from" /></label>
        <label>Đến ngày (UTC)<input type="date" name="date_to" /></label>
        <button type="submit">Áp dụng thời gian</button>
        <button type="reset">Xóa bộ lọc thời gian</button>
      </form>
      {dateError && <p role="alert">{dateError}</p>}
    </Card>
    <section className="dashboard-section">
      <h2>Điểm vai trò và độ tin cậy</h2>
      <RolePanel scope={scope} dates={dates} />
    </section>
    <section className="dashboard-section">
      <h2>Kỹ năng và bằng chứng theo repository</h2>
      <RepoPanel key={scope} scope={scope} dates={dates} />
    </section>
  </>
}

export function DashboardPage() {
  const { user, isLoading, error } = useAuth()
  return <main className="dashboard-page">
    <header className="dashboard-header">
      <h1>Dashboard Profile</h1>
      <nav className="dashboard-actions" aria-label="Công cụ hồ sơ">
        <Link to="/system-status">Tài khoản và kết nối GitHub</Link>
        {user && <>
          <Link to="/analysis">Phân tích Repository</Link>
          <Link to="/activity">Phân tích hoạt động</Link>
          <Link to="/role-scores">Chi tiết Role Scores</Link>
        </>}
      </nav>
    </header>
    {isLoading && <p role="status">Đang kiểm tra đăng nhập…</p>}
    {error && <p role="alert">{error}</p>}
    {user && <DashboardContent key={user.id} user={user} />}
    {!isLoading && !error && !user && <p>Đăng nhập qua trang Tài khoản để xem hồ sơ.</p>}
  </main>
}
