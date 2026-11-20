import { useRef, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { apiFetch } from '@/shared/api/client'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import './jobMatching.css'

type Scope = 'public' | 'private' | 'combined'
type Level = 'required' | 'preferred'
type Requirement = { skill_key: string; level: Level }
type Match = Requirement & {
  status: 'matched' | 'partial' | 'unknown'
  reason: string
  score: number | null
  confidence: number | null
  evidence: {
    evidence_id: string | null
    repository_id: number
    commit_sha: string | null
    file_path: string | null
    source_scope: Exclude<Scope, 'combined'>
  }[]
}
type Report = {
  skills: Match[]
  required_matched_percent: number | null
  stale_snapshot: boolean
  limitations: string[]
  disclaimer: string
}
type JD = {
  fallback?: { message: string } | null
  required_skills: Pick<Requirement, 'skill_key'>[]
  preferred_skills: Pick<Requirement, 'skill_key'>[]
}
const statusLabels = {
  matched: 'Phù hợp',
  partial: 'Phù hợp một phần',
  unknown: 'Chưa đủ bằng chứng',
}

export function JobMatchingPage() {
  const { user, isLoading } = useAuth()
  if (isLoading) return <p role="status">Đang kiểm tra đăng nhập…</p>
  if (!user) return <p>Bạn cần đăng nhập để đối chiếu JD. <Link to="/">Về Dashboard</Link></p>
  return <MatchingWorkspace key={user.id} />
}

function MatchingWorkspace() {
  const [text, setText] = useState('')
  const [url, setUrl] = useState('')
  const [required, setRequired] = useState('')
  const [preferred, setPreferred] = useState('')
  const [scope, setScope] = useState<Scope>('public')
  const [report, setReport] = useState<Report>()
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const inFlight = useRef(false)

  async function run(kind: 'extract' | 'match') {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setError('')
    setNotice('')
    setReport(undefined)
    try {
      if (kind === 'extract') {
        const jd = await apiFetch<JD>('/jobs/analyze', { method: 'POST', body: text.trim() ? { text: text.trim() } : { url: url.trim() } })
        setRequired(jd.required_skills.map((skill) => skill.skill_key).join(', '))
        setPreferred(jd.preferred_skills.map((skill) => skill.skill_key).join(', '))
        setNotice(jd.fallback?.message ?? 'Đã trích xuất. Kiểm tra và chỉnh danh sách kỹ năng trước khi đối chiếu.')
      } else {
        const toSkills = (value: string, level: Level) =>
          value.split(/[,\n]+/u).map((key) => key.trim()).filter(Boolean)
            .map((skill_key): Requirement => ({ skill_key, level }))
        const skills = [...toSkills(required, 'required'), ...toSkills(preferred, 'preferred')]
        if (!skills.length || skills.length > 80 || skills.some((item) => item.skill_key.length > 100)) {
          setError('Nhập từ 1 đến 80 kỹ năng, mỗi tên tối đa 100 ký tự.')
          return
        }
        setReport(await apiFetch<Report>('/jobs/match', {
          method: 'POST', body: { scope, skills },
        }))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể xử lý yêu cầu.')
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  return (
    <main className="job-matching">
      <div className="pixel-page-heading">
        <span className="pixel-eyebrow">MATCHING / JOB REQUIREMENTS</span>
        <h1>Đối chiếu kỹ năng với JD</h1>
        <p>Phân tích mô tả công việc (JD) và đối chiếu với bằng chứng kỹ năng đã xác minh.</p>
      </div>
      <Link to="/dashboard">← Dashboard</Link>
      <h1>Đối chiếu kỹ năng với JD</h1>
      <p><Link to="/cvs/references">Tra mẫu CV theo công ty và vị trí</Link></p>
      <JobSearch />
      <Card>
        <fieldset disabled={busy}>
          <label htmlFor="job-text">Mô tả công việc (JD)</label>
          <textarea id="job-text" maxLength={50_000} rows={6} value={text}
            onChange={(event) => {
              setText(event.target.value); setReport(undefined); setNotice('')
              setRequired(''); setPreferred('')
            }} />
          <label htmlFor="job-url">Hoặc URL tin tuyển dụng</label>
          <input id="job-url" type="url" value={url} onChange={event => {
            setUrl(event.target.value); setReport(undefined); setNotice('')
            setRequired(''); setPreferred('')
          }} />
          <Button disabled={!text.trim() && !url.trim()} onClick={() => void run('extract')}>Trích xuất kỹ năng</Button>
          <p>Nhập hoặc chỉnh kỹ năng, cách nhau bằng dấu phẩy hoặc xuống dòng.</p>
          <label htmlFor="required-skills">Kỹ năng bắt buộc</label>
          <textarea id="required-skills" maxLength={8_080} rows={2} value={required}
            onChange={(event) => { setRequired(event.target.value); setReport(undefined) }} />
          <label htmlFor="preferred-skills">Kỹ năng ưu tiên</label>
          <textarea id="preferred-skills" maxLength={8_080} rows={2} value={preferred}
            onChange={(event) => { setPreferred(event.target.value); setReport(undefined) }} />
          <label htmlFor="job-scope">Phạm vi bằng chứng</label>
          <select id="job-scope" value={scope} onChange={(event) => {
            setScope(event.target.value as Scope); setReport(undefined)
          }}>
            <option value="public">Công khai</option>
            <option value="private">Riêng tư (cần consent)</option>
            <option value="combined">Kết hợp</option>
          </select>
          <Button variant="primary" onClick={() => void run('match')}>Đối chiếu kỹ năng</Button>
        </fieldset>
        {busy && <p role="status">Đang xử lý…</p>}
        {notice && <p role="status">{notice}</p>}
        {error && <p role="alert">{error}</p>}
      </Card>
      {report && (
        <Card>
          <h2>Kết quả đối chiếu</h2>
          <p>Kỹ năng bắt buộc đạt ngưỡng: {report.required_matched_percent === null
            ? 'Chưa đủ dữ liệu để tính tỷ lệ' : `${report.required_matched_percent}%`}</p>
          <p>{report.disclaimer}</p>
          <p>Ngưỡng đối chiếu: điểm kỹ năng ≥ 70 và độ tin cậy ≥ 60 trên thang 100.</p>
          {report.stale_snapshot && <p>Có báo cáo cũ hơn 90 ngày. Hãy phân tích lại để cập nhật.</p>}
          {report.limitations.map((message) => <p key={message}>{message}</p>)}
          <ul className="job-matching-results">
            {report.skills.map((skill) => (
              <li key={skill.skill_key}>
                <strong>{skill.skill_key}</strong> · {skill.level === 'required' ? 'Bắt buộc' : 'Ưu tiên'}
                <p>{statusLabels[skill.status]} — {skill.reason}</p>
                {skill.status === 'unknown' && <p>Khoảng trống bằng chứng: cần thêm dữ liệu đã xác minh.</p>}
                {skill.status === 'partial' && <p>Khoảng trống kỹ năng hoặc độ tin cậy: xem điểm và bằng chứng bên dưới.</p>}
                {skill.score !== null && <p>Điểm kỹ năng: {skill.score}/100{skill.confidence !== null
                  && ` · Độ tin cậy: ${skill.confidence.toFixed(1)}/100`}</p>}
                {skill.evidence.length > 0 && (
                  <details>
                    <summary>Bằng chứng ({skill.evidence.length})</summary>
                    <ul>{skill.evidence.map((evidence, index) => (
                      <li key={index}>
                        Repo #{evidence.repository_id} ({evidence.source_scope === 'private' ? 'riêng tư' : 'công khai'})
                        {evidence.file_path && ` · ${evidence.file_path}`}
                        {evidence.commit_sha && ` · commit ${evidence.commit_sha.slice(0, 12)}`}
                        {evidence.evidence_id && ` · mã bằng chứng ${evidence.evidence_id}`}
                      </li>
                    ))}</ul>
                  </details>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </main>
  )
}


type JobSearchResult = {
  jobs: { id: string; title: string; company: string; url: string; location: string | null }[]
  warnings: string[]
}

function JobSearch() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<JobSearchResult>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function search() {
    setBusy(true)
    setResult(undefined)
    setError('')
    try {
      setResult(await apiFetch<JobSearchResult>('/jobs/search', { method: 'POST', timeoutMs: 15_000, body: { query: query.trim() } }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể tìm việc.')
    } finally {
      setBusy(false)
    }
  }

  return <Card>
    <h2>Tìm việc từ Remotive</h2>
    <form onSubmit={event => { event.preventDefault(); if (query.trim() && !busy) void search() }}>
      <label htmlFor="remote-job-query">Từ khóa</label>
      <input id="remote-job-query" value={query} maxLength={200} onChange={event => setQuery(event.target.value)} />
      <Button type="submit" disabled={busy || !query.trim()}>{busy ? 'Đang tìm…' : 'Tìm tin tuyển dụng'}</Button>
    </form>
    {error && <p role="alert">{error}</p>}
    {result?.warnings.map(warning => <p key={warning} role="status">{warning}</p>)}
    {!!result?.jobs.length && <ul>{result.jobs.map(job => <li key={job.id}>
      {/^https?:\/\//i.test(job.url) ? <a href={job.url} target="_blank" rel="noreferrer">{job.title}</a> : job.title}
      {' · '}{job.company}{job.location ? ' · ' + job.location : ''}
    </li>)}</ul>}
  </Card>
}
