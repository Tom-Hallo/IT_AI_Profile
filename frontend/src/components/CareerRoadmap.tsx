import { useEffect, useRef, useState } from 'react'
import { useAuth } from '@/features/auth/useAuth'
import { apiFetch } from '@/shared/api/client'
import { Button } from '@/shared/ui/Button'
import './CareerRoadmap.css'

type Status = 'pending' | 'in_progress' | 'completed'
type Evidence = { id: number | string; commit_sha: string | null; file_path: string | null }
type Milestone = {
  order: number; skill: string; priority: number; objective: string; metric: string
  current_score: number | null; target_score: number; evidence: Evidence[]
}
type Roadmap = { id: number; goal: string; milestones: Milestone[]; evidence_gaps: string[] }
type Progress = { id: number; external_key: string; status: Status; version: number }
type Tracking = {
  milestones: Progress[]
  suggestions: { id: number; milestone_id: number; explanation: string; state: string }[]
}
type History = { id: number; old_status: Status | null; new_status: Status; created_at: string }

const statuses: Record<Status, string> = {
  pending: 'Chưa bắt đầu', in_progress: 'Đang thực hiện', completed: 'Đã hoàn thành',
}

export default function CareerRoadmap() {
  const { user, isLoading } = useAuth()
  if (isLoading) return <p role="status">Đang xác thực…</p>
  if (!user) return <p>Đăng nhập bằng GitHub để lập lộ trình.</p>
  return <RoadmapWorkspace key={user.id} />
}

function RoadmapWorkspace() {
  const [goal, setGoal] = useState('backend')
  const [roadmap, setRoadmap] = useState<Roadmap>()
  const [tracking, setTracking] = useState<Tracking>()
  const [history, setHistory] = useState<{ milestone: number; entries: History[] }>()
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const active = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    active.current = controller
    void (async () => {
      try {
        const items = await apiFetch<Roadmap[]>('/career-roadmaps', { signal })
        let savedId = 0
        try {
          savedId = Number(sessionStorage.getItem('ita-studio-selected-roadmap')) || 0
        } catch {
          // Session storage can be disabled; load from API normally.
        }
        const latest = items.find(item => item.id === savedId && Array.isArray(item.milestones))
          ?? items.slice().reverse().find(item => Array.isArray(item.milestones) && item.goal)
        if (!latest || signal.aborted) return
        setRoadmap(latest)
        if (latest.goal) setGoal(latest.goal)
        setTracking(await apiFetch<Tracking>(`/roadmap-tracking/${latest.id}`, { signal }))
      } catch (err) {
        if (!signal.aborted) setError(err instanceof Error ? err.message : 'Không tải được lộ trình.')
      } finally {
        if (!signal.aborted) setBusy(false)
      }
    })()
    return () => controller.abort()
  }, [])

  async function run(task: (signal: AbortSignal) => Promise<void>) {
    const signal = active.current?.signal
    if (busy || !signal || signal.aborted) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await task(signal)
    } catch (err) {
      if (!signal.aborted) setError(err instanceof Error ? err.message : 'Không cập nhật được lộ trình.')
    } finally {
      if (!signal.aborted) setBusy(false)
    }
  }

  async function create(signal: AbortSignal) {
    const item = await apiFetch<Roadmap>('/career-roadmaps', { method: 'POST', body: { goal }, signal })
    setRoadmap(item)
    try {
      sessionStorage.setItem('ita-studio-selected-roadmap', String(item.id))
    } catch {
      // The newly created roadmap still stays selected in React state.
    }
    setHistory(undefined)
    setTracking(undefined)
    setTracking(await apiFetch<Tracking>(`/roadmap-tracking/${item.id}`, { signal }))
  }

  // Keep JSONB array order as the canonical timeline order; match tracking
  // by stable skill key, not by the row's index in a separate API response.
  const milestones = Array.isArray(roadmap?.milestones) ? roadmap.milestones : []
  const progressBySkill = new Map(
    (tracking?.milestones ?? []).map(item => [item.external_key.toLowerCase(), item]),
  )
  const nextMilestone = milestones.find(m =>
    progressBySkill.get(m.skill?.toLowerCase())?.status !== 'completed',
  )
  const base = roadmap ? `/roadmap-tracking/${roadmap.id}` : ''

  async function saveStatus(progress: Progress, status: Status, signal: AbortSignal) {
    const saved = await apiFetch<Progress>(`${base}/milestones/${progress.id}`, {
      method: 'PATCH', body: { status, expected_version: progress.version }, signal,
    })
    setTracking(previous => previous && { ...previous, milestones: previous.milestones.map(item => item.id === saved.id ? saved : item) })
    setHistory(undefined)
  }

  async function reevaluate(signal: AbortSignal) {
    const result = await apiFetch<{ suggestions: Tracking['suggestions'] }>(`${base}/re-evaluate`, { method: 'POST', signal })
    setTracking(await apiFetch<Tracking>(base, { signal }))
    setNotice(result.suggestions.some(item => item.state === 'pending')
      ? 'Có đề xuất từ kết quả phân tích GitHub.' : 'Chưa có cột mốc mới đạt mục tiêu theo bằng chứng hiện tại.')
  }

  return <main className="career-page">
    <div className="pixel-page-heading">
      <span className="pixel-eyebrow">CAREER / ROADMAP</span>
      <h1>Lộ trình nghề nghiệp</h1>
      <p>Lập mục tiêu học tập và theo dõi tiến độ dựa trên kết quả phân tích GitHub.</p>
    </div>
    <header className="career-header"><h1>Lộ trình nghề nghiệp</h1><p>Lập mục tiêu học tập dựa trên kết quả phân tích GitHub.</p></header>
    <section className="career-toolbar" aria-label="Mục tiêu nghề nghiệp">
      <label htmlFor="career-goal">Vai trò</label>
      <select id="career-goal" value={goal} onChange={e => setGoal(e.target.value)}>
        <option value="backend">Backend Engineer</option><option value="frontend">Frontend Engineer</option>
        <option value="fullstack">Full-stack Engineer</option><option value="devops">DevOps Engineer</option>
      </select>
      <Button disabled={busy} onClick={() => void run(create)}>Tạo lộ trình</Button>
      {roadmap?.milestones?.length ? <Button disabled={busy} onClick={() => void run(reevaluate)}>Đánh giá lại tiến độ</Button> : null}
    </section>
    {busy && <p role="status">Đang cập nhật lộ trình…</p>}
    {error && <p role="alert" className="career-error">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {roadmap && milestones.length > 0 && <p className="muted">Mốc tiếp theo: {nextMilestone?.skill || 'Đã hoàn thành tất cả'}</p>}
    {roadmap && <ol className="career-timeline">{milestones.map((m, index) => {
      const progress = progressBySkill.get(m.skill?.toLowerCase())
      return <li key={m.skill} className="career-milestone">
        <div className="career-step">{m.order ?? index + 1}</div>
        <article className="career-card">
          <div className="career-card-top"><h2>{m.skill}</h2><span className={`career-priority priority-${m.priority}`}>P{m.priority}</span></div>
          <p>{m.objective}</p><p className="career-metric">{m.metric}</p>
          <p className="career-score">Hiện tại {m.current_score ?? 'chưa đủ bằng chứng'} · Mục tiêu {m.target_score}/100</p>
          {Array.isArray(m.evidence) && m.evidence.length > 0 && <details><summary>Bằng chứng ({m.evidence.length})</summary><ul>
            {m.evidence.map((e, i) => <li key={e.id ?? i}><code>{e.file_path || e.id || 'Minh chứng'}</code>{e.commit_sha && <> · commit <code>{e.commit_sha.slice(0, 8)}</code></>}</li>)}
          </ul></details>}
          {progress && <div>
            <label htmlFor={`progress-${progress.id}`}>Tiến độ</label>{' '}
            <select id={`progress-${progress.id}`} disabled={busy} value={progress.status}
              onChange={e => { const status = e.target.value as Status; void run(signal => saveStatus(progress, status, signal)) }}>
              {Object.entries(statuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>{' '}
            <Button disabled={busy} onClick={() => void run(async signal => {
              const entries = await apiFetch<History[]>(`${base}/milestones/${progress.id}/history`, { signal })
              setHistory({ milestone: progress.id, entries })
            })}>Xem lịch sử</Button>
            {history?.milestone === progress.id && (history.entries.length ? <ul>
              {history.entries.map(entry => <li key={entry.id}>
                {new Date(entry.created_at).toLocaleString('vi-VN')} · {entry.old_status ? statuses[entry.old_status] + ' → ' : ''}{statuses[entry.new_status]}
              </li>)}
            </ul> : <p>Chưa có thay đổi tiến độ.</p>)}
            {tracking?.suggestions.filter(item => item.milestone_id === progress.id && item.state === 'pending').map(suggestion => <div key={suggestion.id}>
              <p>{suggestion.explanation}</p>
              {(['apply', 'reject'] as const).map(action => <Button key={action} disabled={busy}
                onClick={() => void run(async signal => {
                  await apiFetch(`${base}/suggestions/${suggestion.id}/${action}`, { method: 'POST', signal })
                  setTracking(await apiFetch<Tracking>(base, { signal }))
                  setHistory(undefined)
                })}>{action === 'apply' ? 'Xác nhận hoàn thành' : 'Bỏ qua đề xuất'}</Button>)}
            </div>)}
          </div>}
        </article>
      </li>
    })}</ol>}
  </main>
}
