import './SkillScores.css'

export type Breakdown = { criterion: string; weight: number; points: number; evidence_ids: number[] }
export type SkillScore = { id: number | null; technology: string; kind: 'language' | 'framework'; status: 'Scored' | 'Insufficient' | 'Unknown'; score: number | null; breakdown: Breakdown[]; explanation: string; rubric_id: number | null; rubric_version?: string }

export function SkillScores({ scores }: { scores: SkillScore[] }) {
  return <section className="skill-grid" aria-label="Skill proficiency scores">
    {scores.map(item => <article className="skill-card" key={item.id ?? `${item.kind}:${item.technology}`}>
      <header><div><span className="skill-kind">{item.kind}</span><h3>{item.technology}</h3></div><span className="skill-version">Rubric {item.rubric_version ?? `#${item.rubric_id}`}</span></header>
      <div className="skill-score" aria-label={item.score === null ? item.status : `${item.score} trên 100`}>
        {item.score === null ? <span className="skill-unavailable">{item.status === 'Insufficient' ? 'Chưa đủ bằng chứng' : 'Chưa xác định'}</span> : <><strong>{item.score}</strong><span>/100</span></>}
      </div>
      {item.score !== null && <div className="skill-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={item.score}><div style={{ width: `${item.score}%` }} /></div>}
      <p>{item.explanation}</p>
      {item.breakdown.length > 0 && <details><summary>Chi tiết trọng số và evidence</summary>
        {item.breakdown.map(b => <div className="skill-metric" key={b.criterion}><span>{b.criterion} ({b.weight}%)</span><strong>{b.points} điểm</strong><small>Evidence IDs: {b.evidence_ids.join(', ')}</small></div>)}
      </details>}
    </article>)}
  </section>
}
