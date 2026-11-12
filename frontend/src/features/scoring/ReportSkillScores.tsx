import { useEffect, useState } from 'react'
import { apiFetch } from '@/shared/api/client'
import { SkillScores, type SkillScore } from './SkillScores'

export function ReportSkillScores({ repoId, reportId }: { repoId: number; reportId: number }) {
  const [state, setState] = useState<{ scores: SkillScore[] } | { failed: true } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void apiFetch<SkillScore[]>(
      `/scoring/repositories/${repoId}/skills?report_id=${reportId}`,
      { signal: controller.signal },
    ).then((scores) => {
      if (!controller.signal.aborted) setState({ scores })
    }).catch(() => {
      if (!controller.signal.aborted) setState({ failed: true })
    })
    return () => controller.abort()
  }, [repoId, reportId])

  return (
    <section className="card" aria-labelledby="report-skills-heading">
      <h3 id="report-skills-heading">Điểm năng lực theo công nghệ</h3>
      {!state ? <p role="status">Đang tải điểm…</p> :
        'failed' in state ? <p role="alert">Chưa tải được điểm cho báo cáo này.</p> :
        state.scores.length ? <SkillScores scores={state.scores} /> :
        <p>Báo cáo này chưa có công nghệ phù hợp để đánh giá.</p>}
    </section>
  )
}
