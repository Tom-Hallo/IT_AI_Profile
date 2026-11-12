import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { apiFetch } from '@/shared/api/client'

type Scope = 'public' | 'private' | 'combined'
type Limitation = { code: string; message: string }
type Role = { role_key: string; name: string }
type Evidence = { evidence_id: string | null; file_path: string | null; commit_sha: string | null }
type Score = {
  status: string
  role_score: number | null
  confidence: number | null
  coverage: number
  rationale: string
  limitations: Limitation[]
  criteria: { key: string; name: string; rationale: string; evidence_refs: Evidence[] }[]
  inputs: {
    skill_snapshot: { snapshot_ref: string | null }
    architecture: { report_ref: string | null }
  }
}
type ScopedScore = { available: boolean; score: Score | null; limitations: Limitation[] }
type Result = Record<Scope, ScopedScore> & { rubric_version: string }

const labels: Record<Scope, string> = { public: 'Công khai', private: 'Riêng tư', combined: 'Kết hợp' }
const scopes: Scope[] = ['public', 'private', 'combined']

function RoleResults({ role }: { role: string }) {
  const [result, setResult] = useState<Result | null>(null)
  const [scope, setScope] = useState<Scope>('public')
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    void apiFetch<Result>(`/role-scoring/roles/${encodeURIComponent(role)}/score/scoped`, {
      signal: controller.signal,
    }).then((body) => {
      if (!controller.signal.aborted) setResult(body)
    }).catch(() => {
      if (!controller.signal.aborted) setFailed(true)
    })
    return () => controller.abort()
  }, [role, attempt])

  if (failed) return <>
    <p role="alert">Không tải được kết quả chấm điểm.</p>
    <button type="button" onClick={() => {
      setFailed(false)
      setAttempt((value) => value + 1)
    }}>Thử lại</button>
  </>
  if (!result) return <p role="status">Đang tính điểm…</p>

  const active = result[scope]
  const score = active.score
  const limitations = [...active.limitations, ...(score?.limitations ?? [])]
  return <>
    <label htmlFor="role-scope">Phạm vi</label>{' '}
    <select id="role-scope" value={scope} onChange={(event) => setScope(event.target.value as Scope)}>
      {scopes.filter((item) => item !== 'private' || result.private.available)
        .map((item) => <option key={item} value={item}>{labels[item]}</option>)}
    </select>
    <section className="card" aria-labelledby="scoped-score-title">
      <h2 id="scoped-score-title">{labels[scope]}</h2>
      <dl className="rows">
        <div className="row"><dt>Điểm năng lực</dt><dd>
          {score?.role_score == null ? 'Chưa đủ bằng chứng' : `${score.role_score}/100`}
        </dd></div>
        <div className="row"><dt>Confidence</dt><dd>
          {score?.confidence == null ? 'Chưa xác định' : `${score.confidence}/100`}
        </dd></div>
        <div className="row"><dt>Độ phủ tiêu chí</dt><dd>
          {score ? new Intl.NumberFormat('vi-VN', { style: 'percent', maximumFractionDigits: 1 }).format(score.coverage) : 'Chưa xác định'}
        </dd></div>
        <div className="row"><dt>Rubric</dt><dd>{result.rubric_version}</dd></div>
        <div className="row"><dt>Snapshot kỹ năng</dt><dd>{score?.inputs.skill_snapshot.snapshot_ref ?? 'Chưa có'}</dd></div>
        <div className="row"><dt>Báo cáo kiến trúc</dt><dd>{score?.inputs.architecture.report_ref ?? 'Chưa có'}</dd></div>
      </dl>
      {score && <p>{score.rationale}</p>}
      {score?.criteria.length ? <details>
        <summary>Lý do theo tiêu chí</summary>
        <ul>{score.criteria.map((item) => <li key={item.key}>
          <strong>{item.name}</strong> — {item.rationale}
          {item.evidence_refs.length > 0 && <ul>
            {item.evidence_refs.map((ref, index) => <li key={index}>
              {ref.file_path ?? ref.evidence_id ?? 'Bằng chứng'}
              {ref.file_path && ref.commit_sha ? ` · ${ref.commit_sha.slice(0, 8)}` : ''}
            </li>)}
          </ul>}
        </li>)}</ul>
      </details> : null}
      {limitations.length > 0 && <>
        <h3>Giới hạn dữ liệu</h3>
        <ul>{[...new Set(limitations.map((item) => item.message))].map((message) => <li key={message}>{message}</li>)}</ul>
      </>}
    </section>
  </>
}

function RoleSelection() {
  const [roles, setRoles] = useState<Role[] | null>(null)
  const [role, setRole] = useState('')
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    void apiFetch<{ roles: Role[] }>('/role-scoring/roles', { signal: controller.signal })
      .then((body) => {
        if (controller.signal.aborted) return
        setRoles(body.roles)
        setRole(body.roles[0]?.role_key ?? '')
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true)
      })
    return () => controller.abort()
  }, [])

  if (failed) return <p role="alert">Không tải được danh sách vai trò.</p>
  if (!roles) return <p role="status">Đang tải danh sách vai trò…</p>
  if (!roles.length) return <p>Chưa có rubric chấm điểm.</p>
  return <>
    <p>
      <label htmlFor="score-role">Vai trò</label>{' '}
      <select id="score-role" value={role} onChange={(event) => setRole(event.target.value)}>
        {roles.map((item) => <option key={item.role_key} value={item.role_key}>{item.name}</option>)}
      </select>
    </p>
    {role && <RoleResults key={role} role={role} />}
  </>
}

export function ScopedRoleScoresPage() {
  const { user, isLoading, error } = useAuth()
  return <main className="status-page">
    <Link to="/">Về trang chính</Link>
    <h1>Điểm năng lực theo vai trò</h1>
    {isLoading && <p role="status">Đang kiểm tra phiên đăng nhập…</p>}
    {error && <p role="alert">{error}</p>}
    {user && <RoleSelection key={user.id} />}
    {!isLoading && !error && !user && <p>Đăng nhập GitHub để xem điểm của bạn.</p>}
  </main>
}
