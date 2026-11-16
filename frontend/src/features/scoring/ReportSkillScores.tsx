import { useEffect, useState } from 'react'
import { apiFetch } from '@/shared/api/client'
import { SkillScores, type SkillScore } from './SkillScores'

export function ReportSkillScores({ repoId, reportId }: { repoId: number; reportId: number }) {
  const [rubricVersion, setRubricVersion] = useState<'2.1.0' | '2.0.0'>('2.1.0')
  const [state, setState] = useState<{ scores: SkillScore[] } | { failed: true } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void apiFetch<SkillScore[]>(
      `/scoring/repositories/${repoId}/skills?report_id=${reportId}&rubric_version=${rubricVersion}`,
      { signal: controller.signal },
    ).then((scores) => {
      if (!controller.signal.aborted) setState({ scores })
    }).catch(() => {
      if (!controller.signal.aborted) setState({ failed: true })
    })
    return () => controller.abort()
  }, [repoId, reportId, rubricVersion])

  return (
    <section className="card" aria-labelledby="report-skills-heading">
      <h3 id="report-skills-heading">Điểm năng lực theo công nghệ</h3>
      <label htmlFor="scoring-rubric-version">Phiên bản rubric: </label>
      <select id="scoring-rubric-version" value={rubricVersion}
        onChange={(event) => { setState(null); setRubricVersion(event.target.value as '2.1.0' | '2.0.0') }}>
        <option value="2.1.0">2.1.0 — Verified evidence</option>
        <option value="2.0.0">2.0.0 — Legacy</option>
      </select>
      {!state ? <p role="status">Đang tải điểm…</p> :
        'failed' in state ? <p role="alert">Chưa tải được điểm cho báo cáo này.</p> :
        state.scores.length ? <SkillScores scores={state.scores} /> :
        <p>Báo cáo này chưa có công nghệ phù hợp để đánh giá.</p>}
    </section>
  )
}
