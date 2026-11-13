import { useEffect, useState } from 'react';
import './CareerRoadmap.css';

type Evidence = { id: number; repository_id: number; commit_sha: string; file_path: string };
type Milestone = { order: number; skill: string; priority: number; objective: string; metric: string; current_score: number | null; target_score: number; gap_type: string; confidence: string; evidence: Evidence[] };
type Roadmap = { id: number; goal: string; milestones: Milestone[]; evidence_gaps: string[] };

export default function CareerRoadmap() {
  const [goal, setGoal] = useState('backend');
  const [roadmap, setRoadmap] = useState<Roadmap | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    fetch('/api/v1/career-roadmaps', { credentials: 'include' })
      .then(async r => { if (!r.ok) throw new Error('Unable to load roadmaps'); return r.json(); })
      .then((items: Roadmap[]) => { if (alive) setRoadmap(items[0] ?? null); })
      .catch(e => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, []);
  async function create() {
    setBusy(true); setError('');
    try {
      const res = await fetch('/api/v1/career-roadmaps', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ goal }) });
      if (!res.ok) throw new Error(`Generation failed (${res.status})`);
      setRoadmap(await res.json() as Roadmap);
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  return <main className="career-page">
    <header className="career-header"><span className="career-eyebrow">CAREER INTELLIGENCE</span><h1>Your growth roadmap</h1><p>Evidence-backed milestones tailored to your target role.</p></header>
    <section className="career-toolbar" aria-label="Career goal"><label htmlFor="career-goal">Target role</label><select id="career-goal" value={goal} onChange={e => setGoal(e.target.value)}><option value="backend">Backend Engineer</option><option value="frontend">Frontend Engineer</option><option value="fullstack">Full-stack Engineer</option><option value="devops">DevOps Engineer</option></select><button disabled={busy} onClick={create}>{busy ? 'Generating…' : 'Generate roadmap'}</button></section>
    {error && <p role="alert" className="career-error">{error}</p>}
    {roadmap && <><div className="career-summary"><strong>{roadmap.milestones.length}</strong> milestones <span>·</span> <strong>{roadmap.evidence_gaps.length}</strong> evidence gaps <span>·</span> {roadmap.goal}</div><ol className="career-timeline">{roadmap.milestones.map(m => <li key={`${roadmap.id}-${m.skill}`} className="career-milestone"><div className="career-step">{m.order}</div><article className="career-card"><div className="career-card-top"><h2>{m.skill}</h2><span className={`career-priority priority-${m.priority}`}>P{m.priority}</span></div><p>{m.objective}</p><p className="career-metric"><strong>Success metric:</strong> {m.metric}</p><p className="career-score">Current: {m.current_score ?? 'Unverified'} · Target: {m.target_score}/100</p>{m.gap_type === 'missing_evidence' && <p className="career-warning">Evidence gap — skill level cannot be confirmed yet.</p>}{m.evidence.length > 0 && <details><summary>{m.evidence.length} evidence reference(s)</summary><ul>{m.evidence.map(e => <li key={e.id}><code>{e.file_path}</code> · commit <code>{e.commit_sha.slice(0, 8)}</code></li>)}</ul></details>}</article></li>)}</ol></>}
  </main>;
}
