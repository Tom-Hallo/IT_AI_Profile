import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { ApiError, apiFetch } from '@/shared/api/client'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import './resumeReferences.css'

type OutcomeStage = 'unknown' | 'screen' | 'interview' | 'offer'

type Reference = {
  id: string
  title: string
  source: string
  source_url: string
  license: string
  rights_url: string
  rights_checked_on: string
  pattern: string
  outcome_status: 'verified' | 'unverified'
  outcome_stage: OutcomeStage
  outcome_evidence_url: string | null
  outcome_evidence_publisher: string | null
}

type SearchResult = {
  mode: 'verified' | 'general' | 'empty'
  references: Reference[]
  disclaimer: string
}

const stages = {
  unknown: 'Chưa rõ',
  screen: 'Qua vòng hồ sơ',
  interview: 'Được mời phỏng vấn',
  offer: 'Có lời mời làm việc',
} satisfies Record<OutcomeStage, string>

const resultNotes = {
  verified: 'Có mẫu kèm bằng chứng kết quả ứng tuyển cho công ty và vị trí đã nhập.',
  general: 'Chưa có mẫu với kết quả ứng tuyển đã xác minh cho công ty và vị trí này. Dưới đây là mẫu chung phù hợp với vị trí.',
  empty: 'Chưa có mẫu đủ điều kiện cho vị trí này. Thử tên chức danh phổ biến hơn, ví dụ Backend Developer hoặc Data Engineer.',
} satisfies Record<SearchResult['mode'], string>

export function ResumeReferencesPage() {
  const { user, isLoading, error } = useAuth()
  if (isLoading) return <p role="status">Đang kiểm tra đăng nhập…</p>
  if (error) return <p role="alert">{error} <Link to="/dashboard">Về Dashboard</Link></p>
  if (!user) return <p>Bạn cần đăng nhập để tra mẫu CV. <Link to="/dashboard">Về Dashboard</Link></p>
  return <Workspace key={user.id} />
}

function Workspace() {
  const [company, setCompany] = useState('')
  const [role, setRole] = useState('')
  const [result, setResult] = useState<SearchResult>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const request = useRef<AbortController | null>(null)

  useEffect(() => () => request.current?.abort(), [])

  function resetResult() {
    setResult(undefined)
    setError('')
  }

  async function search() {
    if (request.current || !company.trim() || !role.trim()) return
    const controller = new AbortController()
    request.current = controller
    setBusy(true)
    resetResult()
    const query = new URLSearchParams({ company: company.trim(), role: role.trim() })
    try {
      const response = await apiFetch<SearchResult>(`/cvs/references?${query}`, {
        signal: controller.signal,
      })
      if (!controller.signal.aborted) setResult(response)
    } catch (err) {
      if (!controller.signal.aborted) {
        const expired = err instanceof ApiError && err.status === 401
        setError(expired
          ? 'Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.'
          : 'Không thể tra mẫu CV lúc này. Hãy thử lại.')
      }
    } finally {
      request.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  return <main className="resume-references">
    <nav aria-label="Điều hướng mẫu CV">
      <Link to="/dashboard">Dashboard</Link>
      <Link to="/cvs">CV của tôi</Link>
      <Link to="/job-matching">Đối chiếu JD</Link>
    </nav>
    <h1>Mẫu CV tham khảo</h1>
    <Card>
      <form onSubmit={(event) => { event.preventDefault(); void search() }}>
        <fieldset disabled={busy}>
          <div>
            <label htmlFor="reference-company">Công ty</label>
            <input id="reference-company" required maxLength={120} value={company}
              placeholder="Ví dụ Microsoft"
              onChange={(event) => { setCompany(event.target.value); resetResult() }} />
          </div>
          <div>
            <label htmlFor="reference-role">Vị trí</label>
            <input id="reference-role" required maxLength={120} value={role}
              placeholder="Ví dụ Backend Developer"
              onChange={(event) => { setRole(event.target.value); resetResult() }} />
          </div>
          <Button variant="primary" type="submit" disabled={!company.trim() || !role.trim()}>
            Tìm mẫu CV
          </Button>
        </fieldset>
      </form>
    </Card>
    {busy && <p role="status">Đang tra nguồn…</p>}
    {error && <p role="alert">{error}</p>}
    {result && <section aria-labelledby="reference-results">
      <h2 id="reference-results">Kết quả tra cứu</h2>
      <p role="status">{resultNotes[result.mode]}</p>
      <p>{result.disclaimer}</p>
      {!!result.references.length && <ul className="resume-references-list">
        {result.references.map((item) => <li key={item.id}>
          <Card>
            <h3>{item.title}</h3>
            <p>{item.pattern}</p>
            <dl>
              <dt>Nguồn</dt>
              <dd>{item.source}</dd>
              <dt>Giấy phép mẫu</dt>
              <dd>{item.license} · kiểm tra ngày {new Date(item.rights_checked_on)
                .toLocaleDateString('vi-VN', { timeZone: 'UTC' })}</dd>
              <dt>Kết quả ứng tuyển</dt>
              <dd>{item.outcome_status === 'verified'
                ? `Đã xác minh (verified) · ${stages[item.outcome_stage]}`
                : 'Chưa xác minh (unverified)'}</dd>
            </dl>
            <div className="resume-reference-links">
              <a href={item.source_url} target="_blank" rel="noopener noreferrer">Mở mẫu gốc</a>
              <a href={item.rights_url} target="_blank" rel="noopener noreferrer">Xem căn cứ sử dụng</a>
              {item.outcome_evidence_url && <a href={item.outcome_evidence_url}
                target="_blank" rel="noopener noreferrer">
                Bằng chứng từ {item.outcome_evidence_publisher}
              </a>}
            </div>
          </Card>
        </li>)}
      </ul>}
    </section>}
  </main>
}
