import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { apiFetch } from '@/shared/api/client'
import { Card } from '@/shared/ui/Card'
import { Button } from '@/shared/ui/Button'
import { SkillScores, type SkillScore } from '@/features/scoring/SkillScores'
import { FindingEvidenceExplorer } from '@/features/github/FindingEvidenceExplorer'
import { fetchRepositories, fetchLatestAnalysis } from '@/features/github/api'
import type { Repository } from '@/features/github/types'
import { ProfileSummary } from './ProfileSummary'
import './DashboardPage.css'

type Scope = 'public' | 'private' | 'combined'

type RoleSummary = {
  role_key: string
  name: string
}

type Limitation = { code: string; message: string }

type RoleScoreResult = {
  available: boolean
  score: {
    status: string
    role_score: number | null
    confidence: number | null
    coverage: number
    rationale: string
    limitations: Limitation[]
  } | null
  limitations: Limitation[]
}

type ScopedResult = Record<Scope, RoleScoreResult> & { rubric_version: string }

const SCOPE_LABELS: Record<Scope, string> = {
  public: 'Công khai',
  private: 'Riêng tư',
  combined: 'Kết hợp',
}

export function DashboardPage() {
  const { user, isLoading: authLoading, error: authError } = useAuth()

  // Roles
  const [roles, setRoles] = useState<RoleSummary[]>([])
  const [selectedRole, setSelectedRole] = useState<string>('')
  const [scope, setScope] = useState<Scope>('public')
  const [roleResult, setRoleResult] = useState<ScopedResult | null>(null)
  const [loadingRoles, setLoadingRoles] = useState(true)
  const [loadingScore, setLoadingScore] = useState(false)

  // Repositories + Skills + Evidence
  const [repos, setRepos] = useState<Repository[]>([])
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(null)
  const [skillScores, setSkillScores] = useState<SkillScore[]>([])
  const [loadingSkills, setLoadingSkills] = useState(false)
  const [latestReport, setLatestReport] = useState<{
    id: number
    commit_sha: string
  } | null>(null)
  const [loadingReport, setLoadingReport] = useState(false)

  const [error, setError] = useState<string | null>(null)

  // 1. Load roles
  useEffect(() => {
    if (!user) return
    const controller = new AbortController()
    setLoadingRoles(true)
    apiFetch<{ roles: RoleSummary[] }>('/role-scoring/roles', { signal: controller.signal })
      .then((data) => {
        setRoles(data.roles ?? [])
        if (data.roles?.length && !selectedRole) {
          setSelectedRole(data.roles[0].role_key)
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : 'Không tải được danh sách role')
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingRoles(false)
      })
    return () => controller.abort()
  }, [user])

  // 2. Load role score theo scope
  useEffect(() => {
    if (!user || !selectedRole) return
    const controller = new AbortController()
    setLoadingScore(true)
    setRoleResult(null)
    apiFetch<ScopedResult>(
      `/role-scoring/roles/${encodeURIComponent(selectedRole)}/score/scoped`,
      { signal: controller.signal },
    )
      .then((data) => {
        if (!controller.signal.aborted) setRoleResult(data)
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : 'Không tải được điểm role')
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingScore(false)
      })
    return () => controller.abort()
  }, [user, selectedRole])

  // 3. Load danh sách repository
  useEffect(() => {
    if (!user) return
    const controller = new AbortController()
    fetchRepositories({ per_page: 50 }, controller.signal)
      .then((res) => {
        const list = res.items ?? []
        setRepos(list)
        if (list.length && selectedRepoId === null) {
          setSelectedRepoId(list[0].id)
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          // Không chặn toàn bộ dashboard nếu chưa sync GitHub
          console.warn('Không tải được repository list', err)
        }
      })
    return () => controller.abort()
  }, [user])

  // 4. Load skill scores + latest analysis khi chọn repo
  useEffect(() => {
    if (!user || !selectedRepoId) {
      setSkillScores([])
      setLatestReport(null)
      return
    }

    const controller = new AbortController()
    setLoadingSkills(true)
    setLoadingReport(true)
    setSkillScores([])
    setLatestReport(null)

    // Skill scores
    apiFetch<SkillScore[]>(
      `/scoring/repositories/${selectedRepoId}/skills?limit=50`,
      { signal: controller.signal },
    )
      .then((data) => {
        if (!controller.signal.aborted) setSkillScores(Array.isArray(data) ? data : [])
      })
      .catch(() => {
        if (!controller.signal.aborted) setSkillScores([])
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingSkills(false)
      })

    // Latest analysis (để lấy reportId + commitSha cho Evidence)
    fetchLatestAnalysis(selectedRepoId, undefined, controller.signal)
      .then((report) => {
        if (!controller.signal.aborted && report) {
          setLatestReport({
            id: report.report_id ?? 0,
            commit_sha: report.commit_sha,
          })
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setLatestReport(null)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingReport(false)
      })

    return () => controller.abort()
  }, [user, selectedRepoId])

  if (authLoading) {
    return (
      <div className="dashboard-page">
        <p role="status">Đang kiểm tra đăng nhập…</p>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="dashboard-page">
        <Card>
          <h1>Dashboard Profile</h1>
          <p>Bạn cần đăng nhập để xem hồ sơ năng lực và bằng chứng.</p>
          <Link to="/system-status">
            <Button variant="primary">Đi tới trang đăng nhập / System Status</Button>
          </Link>
        </Card>
      </div>
    )
  }

  const activeScope = roleResult?.[scope]
  const score = activeScope?.score
  const limitations = [
    ...(activeScope?.limitations ?? []),
    ...(score?.limitations ?? []),
  ]

  return (
    <div className="dashboard-page">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">WORKSPACE / OVERVIEW</p>
          <h1>Dashboard Profile</h1>
          <p className="muted">
            Điểm số, độ tin cậy, phạm vi và bằng chứng từ phân tích thực tế.
          </p>
        </div>
        <div className="dashboard-actions">
          <Link to="/role-scores">
            <Button variant="ghost">Chi tiết Role Scores</Button>
          </Link>
          <Link to="/analysis">
            <Button variant="ghost">Phân tích Repository</Button>
          </Link>
        </div>
      </header>

      {authError && <p role="alert" className="dashboard-error">{authError}</p>}
      {error && <p role="alert" className="dashboard-error">{error}</p>}

      <ProfileSummary user={user} />

      {/* Filters */}
      <Card className="dashboard-filters">
        <div className="filter-row">
          <label htmlFor="role-select">
            Vai trò
            <select
              id="role-select"
              value={selectedRole}
              onChange={(e) => setSelectedRole(e.target.value)}
              disabled={loadingRoles || roles.length === 0}
            >
              {roles.length === 0 && <option value="">Chưa có role</option>}
              {roles.map((r) => (
                <option key={r.role_key} value={r.role_key}>
                  {r.name}
                </option>
              ))}
            </select>
          </label>

          <label htmlFor="scope-select">
            Phạm vi
            <select
              id="scope-select"
              value={scope}
              onChange={(e) => setScope(e.target.value as Scope)}
            >
              {(['public', 'private', 'combined'] as Scope[]).map((s) => (
                <option
                  key={s}
                  value={s}
                  disabled={s === 'private' && roleResult ? !roleResult.private.available : false}
                >
                  {SCOPE_LABELS[s]}
                </option>
              ))}
            </select>
          </label>

          <label htmlFor="repo-select">
            Repository (Skill + Evidence)
            <select
              id="repo-select"
              value={selectedRepoId ?? ''}
              onChange={(e) =>
                setSelectedRepoId(e.target.value ? Number(e.target.value) : null)
              }
              disabled={repos.length === 0}
            >
              {repos.length === 0 && <option value="">Chưa có repository</option>}
              {repos.map((repo) => (
                <option key={repo.id} value={repo.id}>
                  {repo.full_name || repo.name || `#${repo.id}`}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Card>

      {/* Role Score */}
      <section className="dashboard-section">
        <h2>Điểm vai trò & độ tin cậy</h2>
        {loadingScore && <p role="status">Đang tính điểm…</p>}
        {!loadingScore && roleResult && (
          <div className="score-grid">
            <Card className="score-card">
              <div className="score-main">
                <span className="score-label">Điểm vai trò</span>
                <strong className="score-value">
                  {score?.role_score != null ? score.role_score.toFixed(1) : '—'}
                </strong>
                <span className="score-unit">/ 100</span>
              </div>
              <div className="score-meta">
                <span>
                  Confidence:{' '}
                  <strong>
                    {score?.confidence != null
                      ? `${(score.confidence * 100).toFixed(0)}%`
                      : '—'}
                  </strong>
                </span>
                <span>
                  Coverage:{' '}
                  <strong>
                    {score?.coverage != null
                      ? `${(score.coverage * 100).toFixed(0)}%`
                      : '—'}
                  </strong>
                </span>
                <span className="badge">{score?.status ?? 'N/A'}</span>
              </div>
              {score?.rationale && <p className="rationale">{score.rationale}</p>}
              {limitations.length > 0 && (
                <ul className="limitations">
                  {limitations.map((l) => (
                    <li key={l.code}>{l.message}</li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        )}
        {!loadingScore && !roleResult && !error && (
          <p className="muted">Chưa có dữ liệu điểm cho vai trò này.</p>
        )}
      </section>

      {/* Skill Scores */}
      <section className="dashboard-section">
        <h2>Kỹ năng (Skill Scores)</h2>
        {loadingSkills && <p role="status">Đang tải skill scores…</p>}
        {!loadingSkills && skillScores.length > 0 && (
          <SkillScores scores={skillScores} />
        )}
        {!loadingSkills && skillScores.length === 0 && (
          <p className="muted">
            {selectedRepoId
              ? 'Chưa có skill score cho repository này. Hãy chạy phân tích trước.'
              : 'Chọn repository để xem skill scores.'}
          </p>
        )}
      </section>

      {/* Evidence Explorer */}
      <section className="dashboard-section">
        <h2>Evidence Explorer</h2>
        {loadingReport && <p role="status">Đang tải báo cáo phân tích…</p>}
        {!loadingReport && selectedRepoId && latestReport && latestReport.id > 0 && (
          <FindingEvidenceExplorer
            repositoryId={selectedRepoId}
            reportId={latestReport.id}
            commitSha={latestReport.commit_sha}
          />
        )}
        {!loadingReport && selectedRepoId && !latestReport && (
          <Card>
            <p className="muted">
              Chưa có báo cáo phân tích cho repository này. Vào trang Phân tích để chạy
              analysis trước.
            </p>
            <Link to={`/analysis/${selectedRepoId}`}>
              <Button variant="primary">Chạy phân tích Repository</Button>
            </Link>
          </Card>
        )}
        {!selectedRepoId && (
          <p className="muted">Chọn repository ở bộ lọc phía trên để xem evidence.</p>
        )}
      </section>
    </div>
  )
}