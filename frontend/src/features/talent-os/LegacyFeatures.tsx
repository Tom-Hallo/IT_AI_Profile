import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { apiFetch } from '@/shared/api/client'
import { TalentOSLayout } from './TalentOSLayout'
import './LegacyFeatures.css'

type Consent = { consent_type: string; provider?: string | null; granted: boolean }
type ConsentResponse = { consents: Consent[]; policy_version: string }
type Snapshot = { id: string; score: number; created_at: string; rubric_version: string; window_start: string; window_end: string }
type Comparison = { comparable: boolean; score_delta: number; warnings: string[]; skill_deltas: Record<string, number> }
type Milestone = { id: number; title: string; required_skills: string[]; status: string; version: number }
type Suggestion = { id: number; milestone_id: number; action: string; explanation: string; state: string; evidence: {skill: string; ref: string}[] }
type Roadmap = { milestones: Milestone[]; suggestions: Suggestion[] }
type History = { created_at: string; old_status: string | null; new_status: string; source: string }[]
function errorText(error: unknown) { return error instanceof Error ? error.message : 'Có lỗi xảy ra' }
function validId(id: string) { return /^[1-9]\d*$/.test(id) }
function date(value: string) { return new Date(value).toLocaleString('vi-VN') }

export function TalentConsentPage() {
  const [params] = useSearchParams()
  const [repoId, setRepoId] = useState(params.get('repo_id') ?? '')
  const [scope, setScope] = useState('')
  const [access, setAccess] = useState(false)
  const [external, setExternal] = useState(false)
  const [policy, setPolicy] = useState<ConsentResponse | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const base = `/repositories/${repoId}/consents`
  const refresh = useCallback(async () => {
    if (!validId(repoId)) return
    try { setPolicy(await apiFetch<ConsentResponse>(`/repositories/${repoId}/consents`)) }
    catch (error) { setMessage(`Không tải được trạng thái quyền: ${errorText(error)}`) }
  }, [repoId])
  useEffect(() => { if (validId(repoId)) void apiFetch<ConsentResponse>(`/repositories/${repoId}/consents`).then(setPolicy).catch(() => { /* user can retry */ }) }, [repoId])
  async function grant() {
    if (!policy || !access || !external || !validId(repoId)) return
    const paths = scope.split('\n').map(s => s.trim()).filter(Boolean)
    if (!paths.length) { setMessage('Cần ít nhất một đường dẫn trong phạm vi cấp quyền.'); return }
    setBusy(true)
    try {
      await apiFetch(base, { method:'POST', body:{ consent_type:'repository_access', provider:'', scope:paths, policy_version:policy.policy_version, accepted:true } })
      await apiFetch(base, { method:'POST', body:{ consent_type:'external_ai', provider:'openai', scope:paths, policy_version:policy.policy_version, accepted:true } })
      setMessage('Đã lưu hai xác nhận.'); await refresh()
    } catch (error) { setMessage(`Không hoàn tất cấp quyền: ${errorText(error)}. Kiểm tra trạng thái trước khi thử lại.`); await refresh() }
    finally { setBusy(false) }
  }
  async function revoke(type: string, provider = '') {
    if (!validId(repoId)) return
    setBusy(true)
    try { await apiFetch(`${base}/${type}${provider ? `?provider=${encodeURIComponent(provider)}` : ''}`, {method:'DELETE'}); setMessage('Đã gửi yêu cầu thu hồi quyền.'); await refresh() }
    catch (error) { setMessage(`Thu hồi thất bại: ${errorText(error)}`) }
    finally { setBusy(false) }
  }
  return <TalentOSLayout title="Privacy & Consent"><section className="legacy-panel"><h1>Privacy & Consent</h1><p>Chỉ cấp quyền cho repository và đường dẫn bạn lựa chọn. Hai xác nhận độc lập là bắt buộc trước khi dùng AI bên ngoài.</p>
    <div className="legacy-form"><label>Repository ID<input value={repoId} onChange={e=>{setRepoId(e.target.value);setPolicy(null)}} inputMode="numeric" /></label><label style={{flexBasis:'100%'}}>File paths (mỗi dòng một đường dẫn)<textarea rows={4} value={scope} onChange={e=>setScope(e.target.value)} placeholder="src/main.py" /></label>
    <label className="legacy-check"><input type="checkbox" checked={access} onChange={e=>{setAccess(e.target.checked);if(!e.target.checked)setExternal(false)}} /> Tôi đồng ý cho hệ thống truy cập repository trong phạm vi trên</label>
    <label className="legacy-check"><input type="checkbox" disabled={!access} checked={external} onChange={e=>setExternal(e.target.checked)} /> Tôi đồng ý gửi dữ liệu được phép tới AI bên ngoài (OpenAI)</label>
    <button type="button" disabled={busy||!policy||!validId(repoId)||!access||!external} onClick={()=>void grant()}>Lưu hai xác nhận</button><button type="button" disabled={busy||!validId(repoId)} onClick={()=>void refresh()}>Làm mới</button></div>
    <div className="legacy-card"><h2>Trạng thái quyền</h2>{policy ? <>{policy.consents.length ? policy.consents.map((c,i)=><p key={i}>{c.consent_type}{c.provider ? ` (${c.provider})` : ''}: {c.granted?'Đã cấp':'Đã thu hồi'}</p>) : <p>Chưa cấp quyền</p>}<p className="legacy-muted">Policy version: {policy.policy_version}</p></> : <p>Chưa có dữ liệu trạng thái.</p>}
    <button type="button" disabled={busy||!validId(repoId)} onClick={()=>void revoke('repository_access')}>Thu hồi quyền repository</button><button type="button" disabled={busy||!validId(repoId)} onClick={()=>void revoke('external_ai','openai')}>Thu hồi quyền AI bên ngoài</button></div><p role="status">{message}</p></section></TalentOSLayout>
}

export function TalentHistoryPage() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [oldId, setOldId] = useState('')
  const [newId, setNewId] = useState('')
  const [comparison, setComparison] = useState<Comparison|null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    setBusy(true)
    try { const data = await apiFetch<Snapshot[]>('/historical/snapshots'); setSnapshots(data);setOldId(data[1]?.id??'');setNewId(data[0]?.id??'');setMessage('') }
    catch (error) { setMessage(`Không thể tải lịch sử: ${errorText(error)}`) }
    finally { setBusy(false) }
  }, [])
  useEffect(()=>{ void apiFetch<Snapshot[]>('/historical/snapshots').then(data => {setSnapshots(data);setOldId(data[1]?.id??'');setNewId(data[0]?.id??'')}).catch(()=>{ /* user can retry */ }) },[])
  async function compare() {
    if (!oldId || !newId || oldId===newId) {setMessage('Hãy chọn hai lần đánh giá khác nhau.');return}
    setBusy(true)
    try {setComparison(await apiFetch<Comparison>(`/historical/compare?${new URLSearchParams({old_id:oldId,new_id:newId})}`));setMessage('')}
    catch(error){setMessage(`Không thể so sánh: ${errorText(error)}`)}
    finally{setBusy(false)}
  }
  return <TalentOSLayout title="Historical Scoring"><section className="legacy-panel"><h1>Historical Scoring</h1><p>Lịch sử chấm điểm theo phiên bản rubric và khoảng thời gian đánh giá.</p><button type="button" disabled={busy} onClick={()=>void load()}>Làm mới</button>
    <div className="legacy-grid">{snapshots.map(s=><article className="legacy-card" key={s.id}><h2>{s.score}/100</h2><p>{date(s.created_at)}</p><p>Rubric {s.rubric_version}</p><p className="legacy-muted">{date(s.window_start)} – {date(s.window_end)}</p></article>)}</div>{!snapshots.length&&!message&&<p>Chưa có lịch sử đánh giá.</p>}
    <div className="legacy-form"><label>Đánh giá cũ<select value={oldId} onChange={e=>setOldId(e.target.value)}>{snapshots.map(s=><option key={s.id} value={s.id}>{date(s.created_at)} · {s.score}/100</option>)}</select></label><label>Đánh giá mới<select value={newId} onChange={e=>setNewId(e.target.value)}>{snapshots.map(s=><option key={s.id} value={s.id}>{date(s.created_at)} · {s.score}/100</option>)}</select></label><button type="button" disabled={busy||snapshots.length<2} onClick={()=>void compare()}>So sánh</button></div>
    {comparison&&<div className="legacy-card"><h2>{comparison.comparable?`Chênh lệch: ${comparison.score_delta>0?'+':''}${comparison.score_delta}`:'Không thể so sánh trực tiếp'}</h2>{comparison.warnings?.map((w,i)=><p key={i}>{w}</p>)}{comparison.comparable&&Object.entries(comparison.skill_deltas??{}).map(([skill,delta])=><p key={skill}>{skill}: {delta>0?'+':''}{delta}</p>)}</div>}<p role="status" className="legacy-error">{message}</p></section></TalentOSLayout>
}

export function TalentRoadmapTrackingPage() {
  const [params] = useSearchParams()
  const [id,setId] = useState(params.get('roadmap_id')??'')
  const [data,setData] = useState<Roadmap|null>(null)
  const [message,setMessage] = useState('')
  const [busy,setBusy] = useState(false)
  const [history,setHistory] = useState<Record<number,History>>({})
  const base = `/roadmap-tracking/${id}`
  const load = useCallback(async () => {
    if (!validId(id)) {setMessage('Nhập Roadmap ID hợp lệ.');return}
    setBusy(true)
    try {setData(await apiFetch<Roadmap>(`/roadmap-tracking/${id}`));setMessage('Đã tải roadmap.')}
    catch(error){setMessage(`Không thể tải roadmap: ${errorText(error)}`)}
    finally{setBusy(false)}
  },[id])
  useEffect(()=>{if(validId(id))void apiFetch<Roadmap>(`/roadmap-tracking/${id}`).then(setData).catch(()=>{ /* user can retry */ })},[id])
  async function update(m:Milestone,status:string,note:string){setBusy(true);try{await apiFetch(`${base}/milestones/${m.id}`,{method:'PATCH',body:{status,note:note||null,expected_version:m.version}});await load()}catch(error){setMessage(`Cập nhật thất bại: ${errorText(error)}`)}finally{setBusy(false)}}
  async function showHistory(m:Milestone){try{const entries=await apiFetch<History>(`${base}/milestones/${m.id}/history`);setHistory(v=>({...v,[m.id]:entries}))}catch(error){setMessage(errorText(error))}}
  async function suggestion(id:number,action:'apply'|'reject'){setBusy(true);try{await apiFetch(`${base}/suggestions/${id}/${action}`,{method:'POST'});await load()}catch(error){setMessage(`Không thể xử lý đề xuất: ${errorText(error)}`)}finally{setBusy(false)}}
  return <TalentOSLayout title="Roadmap Tracking"><section className="legacy-panel"><h1>Roadmap Tracking</h1><p>Theo dõi tiến độ học tập, lịch sử milestone và các đề xuất dựa trên evidence.</p><div className="legacy-form"><label>Roadmap ID<input value={id} onChange={e=>setId(e.target.value)} inputMode="numeric" /></label><button type="button" disabled={busy||!validId(id)} onClick={()=>void load()}>Tải roadmap</button></div>
    <h2>Milestones</h2>{data?.milestones.map(m=><MilestoneCard key={m.id} milestone={m} busy={busy} history={history[m.id]} onSave={(status,note)=>void update(m,status,note)} onHistory={()=>void showHistory(m)} />)}{data&&data.milestones.length===0&&<p>Chưa có milestone.</p>}
    <h2>Đề xuất đang chờ ({data?.suggestions.filter(s=>s.state==='pending').length??0})</h2>{data?.suggestions.filter(s=>s.state==='pending').map(s=><div className="legacy-card" key={s.id}><h3>Milestone #{s.milestone_id} · {s.action}</h3><p>{s.explanation}</p><p className="legacy-muted">{s.evidence.map(e=>`${e.skill}: ${e.ref}`).join(' · ')}</p><button type="button" disabled={busy} onClick={()=>void suggestion(s.id,'apply')}>Chấp nhận</button><button type="button" disabled={busy} onClick={()=>void suggestion(s.id,'reject')}>Từ chối</button></div>)}<p role="status">{message}</p><p><Link to="/talent-os">Quay lại Dashboard</Link></p></section></TalentOSLayout>
}
function MilestoneCard({milestone:m,busy,history,onSave,onHistory}:{milestone:Milestone;busy:boolean;history?:History;onSave:(status:string,note:string)=>void;onHistory:()=>void}){
 const [status,setStatus]=useState(m.status);const [note,setNote]=useState('')
 return <article className="legacy-card"><h3>{m.title}</h3><p>Skills: {m.required_skills.join(', ')||'—'}</p><div className="legacy-form"><label>Trạng thái<select value={status} onChange={e=>setStatus(e.target.value)}><option value="pending">Pending</option><option value="in_progress">In Progress</option><option value="completed">Completed</option></select></label><label>Ghi chú<input value={note} onChange={e=>setNote(e.target.value)} /></label><button type="button" disabled={busy} onClick={()=>onSave(status,note)}>Lưu tiến độ</button><button type="button" disabled={busy} onClick={onHistory}>Lịch sử</button></div>{history&&<div>{history.length?history.map((h,i)=><p key={i}>{date(h.created_at)}: {h.old_status??'—'} → {h.new_status} ({h.source})</p>):<p>Chưa có lịch sử.</p>}</div>}</article>
}
