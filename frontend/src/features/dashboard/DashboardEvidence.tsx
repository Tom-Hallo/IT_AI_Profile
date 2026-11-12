import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { FindingEvidenceExplorer } from '@/features/github/FindingEvidenceExplorer'
import type { CollaborationEvidenceListResult } from '@/features/github/types'
import { SkillScores, type SkillScore } from '@/features/scoring/SkillScores'
import { useDashboardQuery } from './useDashboardQuery'

type Report = { id: number; commit_sha: string; analyzed_at: string }

function ReportSkills({ repoId, reportId }: { repoId: number; reportId: number }) {
  const { state, retry } = useDashboardQuery<SkillScore[]>(
    `/scoring/repositories/${repoId}/skills?report_id=${reportId}`,
  )
  if (state.phase === 'loading') return <p role="status">Đang tải kỹ năng…</p>
  if (state.phase === 'error') return <p role="alert">
    Không tải được kỹ năng. <button type="button" onClick={retry}>Thử lại</button>
  </p>
  return state.data.length ? <SkillScores scores={state.data} /> : <p>Báo cáo chưa có điểm kỹ năng.</p>
}

function PullRequestEvidence({ repoId, dates }: { repoId: number; dates: string }) {
  const [pr, setPr] = useState('')
  const [page, setPage] = useState(1)
  const query = new URLSearchParams(dates)
  query.set('per_page', '10')
  query.set('page', String(page))
  query.set('evidence_type', 'pull_request')
  if (pr) query.set('pr_number', pr)
  const { state, retry } = useDashboardQuery<CollaborationEvidenceListResult>(
    `/repositories/${repoId}/collaboration/evidence?${query}`,
  )
  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPr(String(new FormData(event.currentTarget).get('pr') ?? '').trim())
    setPage(1)
  }
  return <section className="card">
    <h3>Bằng chứng Pull Request</h3>
    <form onSubmit={search}>
      <label>Số PR <input type="number" name="pr" min={1} max={2147483647} step={1} /></label>{' '}
      <button type="submit">Lọc PR</button>
    </form>
    {state.phase === 'loading' && <p role="status">Đang tải bằng chứng PR…</p>}
    {state.phase === 'error' && <p role="alert">
      Không tải được bằng chứng PR. <button type="button" onClick={retry}>Thử lại</button>
    </p>}
    {state.phase === 'ready' && <>
      {state.data.items.length === 0 ? <p>Chưa có bằng chứng PR phù hợp.</p> :
        <ul>{state.data.items.map((item, index) => <li key={item.id ?? index}>
          <strong>{item.pr_number ? `PR #${item.pr_number}` : item.target_identifier}</strong>
          {item.state && <span> · {item.state}</span>}
          {item.recorded_at && <span> · {item.recorded_at.slice(0, 10)}</span>}
          {item.rationale && <p>{item.rationale}</p>}
        </li>)}</ul>}
      {state.data.total > 10 && <nav className="dashboard-actions" aria-label="Trang bằng chứng PR">
        <button type="button" disabled={page === 1} onClick={() => setPage(page - 1)}>Trang trước</button>
        <span>{page}/{Math.ceil(state.data.total / 10)}</span>
        <button type="button" disabled={page * 10 >= state.data.total} onClick={() => setPage(page + 1)}>Trang sau</button>
      </nav>}
    </>}
  </section>
}

export function DashboardEvidence({ repoId, dates }: { repoId: number; dates: string }) {
  const { state, retry } = useDashboardQuery<Report | null>(
    `/repositories/${repoId}/analysis/dashboard-report?${dates}`,
  )
  if (state.phase === 'loading') return <p role="status">Đang tải báo cáo…</p>
  if (state.phase === 'error') return <p role="alert">
    Không tải được báo cáo. Hãy kiểm tra quyền và consent.{' '}
    <button type="button" onClick={retry}>Thử lại</button>
  </p>
  const report = state.data
  return <>
    {report ? <>
      <p>Báo cáo #{report.id} · {new Date(report.analyzed_at).toLocaleString('vi-VN')}</p>
      <ReportSkills key={report.id} repoId={repoId} reportId={report.id} />
      <FindingEvidenceExplorer key={report.id} repositoryId={repoId} reportId={report.id} commitSha={report.commit_sha} />
    </> : <p>Chưa có báo cáo trong khoảng đã chọn. <Link to={`/analysis/${repoId}`}>Mở phân tích</Link></p>}
    <PullRequestEvidence repoId={repoId} dates={dates} />
  </>
}
