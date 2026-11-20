import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { ApiError, apiFetch } from '@/shared/api/client'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'

type Field = 'full_name' | 'public_repositories'
type PublicProfile = {
  full_name?: string
  public_repositories?: { name: string; url: string; language: string | null }[]
}
type Share = { id: number; allowed_fields: Field[] }
const fields: Record<Field, string> = { full_name: 'Tên hiển thị', public_repositories: 'Repository công khai' }

function SharedFields({ profile }: { profile: PublicProfile }) {
  return <>
    {profile.full_name && <p>{profile.full_name}</p>}
    {profile.public_repositories && <section>
      <h2>Repository công khai</h2>
      {profile.public_repositories.length === 0 && <p>Chưa có repository công khai được chia sẻ.</p>}
      <ul>{profile.public_repositories.map(repo => <li key={repo.url}>
        <a href={repo.url} target="_blank" rel="noreferrer">{repo.name}</a>
        {repo.language && ' · ' + repo.language}
      </li>)}</ul>
    </section>}
    {!profile.full_name && !profile.public_repositories && <p>Hồ sơ chưa có mục nào được chia sẻ.</p>}
  </>
}

export function PublicProfilePage() {
  const { token } = useParams()
  return <PublicProfile key={token} token={token ?? ''} />
}

function PublicProfile({ token }: { token: string }) {
  const [profile, setProfile] = useState<PublicProfile>()
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    apiFetch<PublicProfile>(`/public/profiles/${encodeURIComponent(token)}`, { signal: controller.signal })
      .then(setProfile)
      .catch(err => {
        if (!controller.signal.aborted) {
          setError(err instanceof ApiError && err.status === 404
            ? 'Liên kết đã bị thu hồi hoặc không tồn tại.'
            : 'Không tải được hồ sơ. Hãy thử lại.')
        }
      })
    return () => controller.abort()
  }, [token])
  return <main className="pixel-main">
    <Card>
      <h1>Hồ sơ được chia sẻ</h1>
      {error ? <p role="alert">{error}</p>
        : profile ? <SharedFields profile={profile} /> : <p role="status">Đang tải hồ sơ…</p>}
      <Link to="/">IT Talent AI Profile</Link>
    </Card>
  </main>
}

export function ProfileSharingPage() {
  const { user, isLoading } = useAuth()
  if (isLoading) return <p role="status">Đang xác thực…</p>
  if (!user) return <p>Đăng nhập bằng GitHub để chia sẻ hồ sơ.</p>
  return <ShareWorkspace key={user.id} />
}

function ShareWorkspace() {
  const [allowed, setAllowed] = useState<Field[]>(['full_name'])
  const [links, setLinks] = useState<Share[]>([])
  const [current, setCurrent] = useState<{ id: number; url: string }>()
  const [profile, setProfile] = useState<PublicProfile>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    apiFetch<Share[]>('/profile/shares', { signal: controller.signal })
      .then(setLinks)
      .catch(err => { if (!controller.signal.aborted) setError(err.message) })
    return () => controller.abort()
  }, [])

  async function change(action: 'preview' | 'create' | 'revoke', id?: number) {
    setBusy(true)
    setError('')
    try {
      if (action === 'preview') {
        setProfile(await apiFetch<PublicProfile>('/profile/shares/preview', {
          method: 'POST', body: { allowed_fields: allowed },
        }))
      } else if (action === 'create') {
        const result = await apiFetch<Share & { token: string }>('/profile/shares', {
          method: 'POST', body: { allowed_fields: allowed },
        })
        setCurrent({ id: result.id, url: new URL(`/share/${result.token}`, location.origin).href })
        setLinks(previous => [result, ...previous])
      } else {
        await apiFetch(`/profile/shares/${id}`, { method: 'DELETE' })
        setLinks(previous => previous.filter(link => link.id !== id))
        setCurrent(previous => previous?.id === id ? undefined : previous)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể cập nhật liên kết.')
    } finally {
      setBusy(false)
    }
  }

  return <section>
    <div className="pixel-page-heading">
      <span className="pixel-eyebrow">PROFILE / PUBLIC SHARING</span>
      <h1>Chia sẻ hồ sơ</h1>
      <p>Quản lý các liên kết chia sẻ hồ sơ ứng viên và quyền truy cập dữ liệu.</p>
    </div>
    <Card>
      <fieldset disabled={busy}>
        <legend>Thông tin cho phép hiển thị</legend>
        {Object.entries(fields).map(([key, label]) => <label key={key} style={{ display: 'block' }}>
          <input type="checkbox" checked={allowed.includes(key as Field)} onChange={event => {
            const checked = event.target.checked
            setAllowed(previous => checked ? [...previous, key as Field] : previous.filter(x => x !== key))
            setProfile(undefined)
          }} /> {label}
        </label>)}
        <Button disabled={!allowed.length} onClick={() => void change('preview')}>Xem trước</Button>{' '}
        <Button disabled={!allowed.length} onClick={() => void change('create')}>Tạo liên kết</Button>
      </fieldset>
      {profile && <SharedFields profile={profile} />}
      {current && <p><a href={current.url}>{current.url}</a>. Sao chép liên kết trước khi rời trang.</p>}
      {error && <p role="alert">{error}</p>}
    </Card>
    <Card>
      <h2>Liên kết đang hoạt động</h2>
      {!links.length && <p>Chưa có liên kết đang hoạt động.</p>}
      <ul>{links.map(link => <li key={link.id}>
        #{link.id} · {link.allowed_fields.map(field => fields[field]).join(', ')}{' '}
        <Button disabled={busy} onClick={() => void change('revoke', link.id)}>Thu hồi</Button>
      </li>)}</ul>
    </Card>
  </section>
}
