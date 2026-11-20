import { useEffect, useState } from 'react'
import { useAuth } from '@/features/auth/useAuth'
import { ConsentManager } from '@/features/privacy/ConsentManager'
import { fetchRepositories } from '@/features/github/api'
import type { Repository } from '@/features/github/types'
export function PixelPrivacyPage() {
  const { user, isLoading } = useAuth()
  if (isLoading) return <p role="status">Đang xác thực…</p>
  if (!user) return <p>Đăng nhập bằng GitHub để quản lý quyền truy cập.</p>
  return (
    <div>
      <div className="pixel-page-heading">
        <p className="pixel-eyebrow">DATA &amp; CONSENT</p>
        <h1>Privacy &amp; consent</h1>
        <p>Quản lý quyền truy cập theo từng repository. Dữ liệu riêng tư chỉ được xử lý sau khi bạn cấp phép rõ ràng.</p>
      </div>
      <div className="pixel-content-panel">
        <PrivacyWorkspace key={user.id} />
      </div>
    </div>
  )
}

function PrivacyWorkspace() {
  const [repos, setRepos] = useState<Repository[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    void fetchRepositories({ per_page: 100 }, controller.signal).then(value => {
      if (!controller.signal.aborted) { setRepos(value.items); setSelected(value.items[0]?.id ?? null) }
    }).catch(() => { if (!controller.signal.aborted) setError('Không thể tải repositories. Vui lòng đăng nhập GitHub.') })
    return () => controller.abort()
  }, [])
  return <section>
    {error && <p role="alert">{error}</p>}
    {repos.length > 0 && <><label htmlFor="pixel-consent-repo">Repository</label>{' '}
      <select id="pixel-consent-repo" value={selected ?? ''} onChange={event => setSelected(Number(event.target.value))}>
        {repos.map(repo => <option key={repo.id} value={repo.id}>{repo.full_name}</option>)}
      </select></>}
    {selected !== null ? <ConsentManager key={selected} repoId={selected} /> : <p>Chưa có repository để quản lý consent.</p>}
  </section>
}
