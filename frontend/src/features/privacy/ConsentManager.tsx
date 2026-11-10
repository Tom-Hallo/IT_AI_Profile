import { useEffect, useState } from 'react'
import './ConsentManager.css'

type Consent = { consent_type: 'repository_access' | 'external_ai'; provider: string; granted: boolean; revoked_at: string | null }
type Response = { policy_version: string; consents: Consent[] }
type Cleanup = { job_id: string; status: string; reason: string }

export function ConsentManager({ repoId }: { repoId: number }) {
  const [consents, setConsents] = useState<Consent[]>([])
  const [cleanups, setCleanups] = useState<Cleanup[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const refresh = async () => {
    const [a, b] = await Promise.all([
      fetch(`/api/v1/repositories/${repoId}/consents`, { credentials: 'same-origin', cache: 'no-store' }),
      fetch(`/api/v1/repositories/${repoId}/consents/cleanup`, { credentials: 'same-origin', cache: 'no-store' }),
    ])
    if (!a.ok || !b.ok) throw new Error('Cannot load consent status')
    setConsents(((await a.json()) as Response).consents)
    setCleanups((await b.json()) as Cleanup[])
  }
  useEffect(() => {
    let active = true
    Promise.all([
      fetch(`/api/v1/repositories/${repoId}/consents`, { credentials: 'same-origin' }),
      fetch(`/api/v1/repositories/${repoId}/consents/cleanup`, { credentials: 'same-origin' }),
    ]).then(async ([a, b]) => {
      if (!a.ok || !b.ok) throw new Error('Load failed')
      const consentsData = (await a.json()) as Response
      const cleanupData = (await b.json()) as Cleanup[]
      if (active) { setConsents(consentsData.consents); setCleanups(cleanupData) }
    }).catch(() => { if (active) setError('Không thể tải quyền truy cập') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [repoId])
  const revoke = async (item: Consent) => {
    if (!window.confirm('Thu hồi quyền? Job đang chạy sẽ bị hủy và dữ liệu tạm được dọn sau khi worker dừng.')) return
    setBusy(true); setError('')
    try {
      const provider = item.consent_type === 'external_ai' ? `?provider=${encodeURIComponent(item.provider)}` : ''
      const response = await fetch(`/api/v1/repositories/${repoId}/consents/${item.consent_type}${provider}`, {
        method: 'DELETE', credentials: 'same-origin', headers: { Accept: 'application/json' },
      })
      if (!response.ok) throw new Error('Revoke failed')
      await refresh()
    } catch { setError('Không thể thu hồi quyền hoặc tải trạng thái mới') }
    finally { setBusy(false) }
  }
  return <section className="consent-manager" aria-label="Quản lý quyền riêng tư">
    <header><span className="consent-icon">✦</span><div><h2>Privacy & Permissions</h2><p>Quyền truy cập mã nguồn và xử lý AI</p></div></header>
    {loading && <p>Đang tải...</p>}
    {error && <p role="alert" className="consent-error">{error}</p>}
    {consents.map(item => <div className="consent-item" key={`${item.consent_type}:${item.provider}`}>
      <div><strong>{item.consent_type === 'repository_access' ? 'Private Repository Access' : `External AI · ${item.provider}`}</strong><p>{item.granted ? 'Đang cấp quyền' : 'Đã thu hồi'}</p></div>
      <button type="button" disabled={!item.granted || busy} onClick={() => void revoke(item)}>{item.granted ? 'Thu hồi' : 'Đã thu hồi'}</button>
    </div>)}
    <div className="consent-cleanups"><h3>Temporary data cleanup</h3>
      {cleanups.length === 0 ? <p>Chưa có yêu cầu dọn dữ liệu.</p> : cleanups.map(c => <p key={c.job_id}>Job {c.job_id.slice(0, 8)}: <strong>{c.status}</strong></p>)}
      <button type="button" disabled={busy} onClick={() => void refresh().catch(() => setError('Không thể làm mới trạng thái'))}>Làm mới trạng thái</button>
    </div>
  </section>
}
