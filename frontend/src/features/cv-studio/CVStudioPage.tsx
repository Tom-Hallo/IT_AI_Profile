import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { ApiError, apiFetch } from '@/shared/api/client'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import './cvStudio.css'

type Template = 'classic' | 'technical'
type Source = {
  type: 'cv' | 'github' | 'manual' | 'missing'
  cv_id?: number
  cv_version?: number
  line_number?: number
  repo_id?: number
  evidence_id?: string
  commit_sha?: string
}
type Line = { text: string; source: Source }
type Version = {
  document_id: string
  number: number
  title: string
  template: Template
  created_at: string
}
type Detail = Version & { lines: Line[]; source_unavailable: boolean }
type CVSource = { id: number; uploaded_at: string }

const PAGE_SIZE = 50
const endpoint = '/cv-studio'

function errorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.'
    if (error.status === 403) return 'Yêu cầu bị từ chối. Hãy mở lại trang từ địa chỉ chính của ứng dụng.'
    const body = error.body
    if (typeof body === 'object' && body && 'detail' in body && typeof body.detail === 'string') {
      return body.detail
    }
    return error.message
  }
  return 'Không thể xử lý yêu cầu CV Studio.'
}

function citation(source: Source) {
  if (source.type === 'cv') {
    return <>CV #{source.cv_id} · bản {source.cv_version} · dòng {source.line_number}</>
  }
  if (source.type === 'github') {
    return <>
      <Link to={`/repositories/${source.repo_id}/analysis`}>Repo #{source.repo_id}</Link>
      {' · '} commit <code>{source.commit_sha}</code>
      {' · '} bằng chứng <code>{source.evidence_id}</code>
    </>
  }
  return 'Người dùng chỉnh sửa'
}

function Pagination({ offset, size, busy, onPage }: {
  offset: number; size: number; busy: boolean; onPage: (offset: number) => void
}) {
  return <div className="cv-studio-actions">
    {offset > 0 && <Button disabled={busy} onClick={() => onPage(offset - PAGE_SIZE)}>Trang trước</Button>}
    {size === PAGE_SIZE && <Button disabled={busy} onClick={() => onPage(offset + PAGE_SIZE)}>Trang sau</Button>}
  </div>
}

export function CVStudioPage() {
  const { user, isLoading } = useAuth()
  if (isLoading) return <p role="status">Đang kiểm tra đăng nhập…</p>
  if (!user) return <p>Bạn cần đăng nhập để sử dụng CV Studio. <Link to="/">Về Dashboard</Link></p>
  return <Workspace key={user.id} />
}

function Workspace() {
  const [documents, setDocuments] = useState<Version[]>([])
  const [documentsOffset, setDocumentsOffset] = useState(0)
  const [versions, setVersions] = useState<Version[]>([])
  const [versionsOffset, setVersionsOffset] = useState(0)
  const [latestNumber, setLatestNumber] = useState(0)
  const [cvs, setCvs] = useState<CVSource[]>([])
  const [nextCV, setNextCV] = useState<number>()
  const [selectedCV, setSelectedCV] = useState('')
  const [useGitHub, setUseGitHub] = useState(true)
  const [permission, setPermission] = useState(false)
  const [template, setTemplate] = useState<Template>('classic')
  const [title, setTitle] = useState('')
  const [jd, setJD] = useState('')
  const [detail, setDetail] = useState<Detail>()
  const [editTitle, setEditTitle] = useState('')
  const [editText, setEditText] = useState('')
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const session = useRef<AbortController | null>(null)
  const running = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    session.current = controller
    Promise.allSettled([
      apiFetch<Version[]>(endpoint, { signal }).then((items) => { if (!signal.aborted) setDocuments(items) }),
      apiFetch<CVSource[]>('/cvs', { signal }).then((items) => {
        if (signal.aborted) return
        setCvs(items)
        setNextCV(items.length === PAGE_SIZE ? items.at(-1)?.id : undefined)
      }),
    ]).then((results) => {
      if (signal.aborted) return
      const failed = results.find((result) => result.status === 'rejected')
      if (failed) setError(errorMessage(failed.reason))
      setBusy(false)
    })
    return () => controller.abort()
  }, [])

  async function run(task: (signal: AbortSignal) => Promise<void>) {
    const signal = session.current?.signal
    if (!signal || signal.aborted || running.current) return
    running.current = true
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await task(signal)
    } catch (err) {
      if (!signal.aborted) setError(errorMessage(err))
    } finally {
      running.current = false
      if (!signal.aborted) setBusy(false)
    }
  }

  function show(version: Detail) {
    setDetail(version)
    setEditTitle(version.title)
    setEditText(version.lines.filter((line) => line.source.type !== 'missing').map((line) => line.text).join('\n'))
  }

  function updateDocuments(version: Version) {
    setDocuments((current) => [
      version, ...current.filter((item) => item.document_id !== version.document_id),
    ].slice(0, PAGE_SIZE))
  }

  async function loadDocuments(offset: number, signal: AbortSignal) {
    const items = await apiFetch<Version[]>(`${endpoint}?offset=${offset}`, { signal })
    if (signal.aborted) return
    setDocumentsOffset(offset)
    setDocuments(items)
  }

  async function loadVersions(document: string, offset: number, signal: AbortSignal) {
    const items = await apiFetch<Version[]>(`${endpoint}/${document}/versions?offset=${offset}`, { signal })
    if (signal.aborted) return
    setVersionsOffset(offset)
    setVersions(items)
    if (offset === 0) setLatestNumber(items[0]?.number ?? 0)
  }

  function loadOlderCVs() {
    if (!nextCV) return
    void run(async (signal) => {
      const items = await apiFetch<CVSource[]>(`/cvs?before_id=${nextCV}`, { signal })
      if (signal.aborted) return
      setCvs((current) => [...current, ...items])
      setNextCV(items.length === PAGE_SIZE ? items.at(-1)?.id : undefined)
    })
  }

  function openVersion(document: string, number: number) {
    void run(async (signal) => {
      const version = await apiFetch<Detail>(`${endpoint}/${document}/versions/${number}`, { signal })
      if (document !== detail?.document_id || number === latestNumber) {
        await loadVersions(document, 0, signal)
      }
      if (!signal.aborted) show(version)
    })
  }

  function generate() {
    void run(async (signal) => {
      const version = await apiFetch<Detail>(`${endpoint}/generate`, {
        method: 'POST', signal, timeoutMs: 330_000,
        body: { title, jd, template, use_github: useGitHub, cv_id: Number(selectedCV) || null, allow_ai: permission },
      })
      if (signal.aborted) return
      show(version)
      setVersions([version])
      setVersionsOffset(0)
      setLatestNumber(version.number)
      setPermission(false)
      setNotice('Đã tạo và lưu bản nháp.')
      if (documentsOffset === 0) updateDocuments(version)
      else await loadDocuments(0, signal)
    })
  }

  function save() {
    if (!detail || detail.number !== latestNumber) return
    void run(async (signal) => {
      const version = await apiFetch<Detail>(`${endpoint}/${detail.document_id}/versions`, {
        method: 'POST', signal,
        body: { title: editTitle, text: editText, previous_version: detail.number },
      })
      if (signal.aborted) return
      show(version)
      setLatestNumber(version.number)
      setNotice(`Đã lưu phiên bản ${version.number}.`)
      if (versionsOffset === 0) setVersions((current) => [version, ...current].slice(0, PAGE_SIZE))
      else await loadVersions(version.document_id, 0, signal)
      if (documentsOffset === 0) updateDocuments(version)
      else await loadDocuments(0, signal)
    })
  }

  function download(format: 'pdf' | 'docx') {
    if (!detail) return
    void run(async (signal) => {
      const path = `${endpoint}/${detail.document_id}/versions/${detail.number}/export?format=${format}`
      const file = await apiFetch<Blob>(path, { signal, responseType: 'blob' })
      if (signal.aborted) return
      const url = URL.createObjectURL(file)
      const link = document.createElement('a')
      link.href = url
      link.download = `cv-v${detail.number}.${format}`
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    })
  }

  const savedText = detail?.lines.filter((line) => line.source.type !== 'missing').map((line) => line.text).join('\n')
  const dirty = detail && (editTitle !== detail.title || editText !== savedText)
  const canEdit = detail && detail.number === latestNumber && !detail.source_unavailable
  const missing = detail?.lines.filter((line) => line.source.type === 'missing') ?? []

  return <main className="cv-studio-page">
    <nav aria-label="Điều hướng CV Studio"><Link to="/">Dashboard</Link> <Link to="/cvs">CV của tôi</Link></nav>
    <h1>AI CV Studio</h1>
    {busy && <p role="status">Đang xử lý…</p>}
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <div className="cv-studio-grid">
      <Card>
        <h2>Tạo bản nháp theo JD</h2>
        <form onSubmit={(event) => { event.preventDefault(); generate() }}>
          <fieldset disabled={busy}>
            <label htmlFor="studio-title">Tên CV</label>
            <input id="studio-title" required maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} />
            <label htmlFor="studio-jd">Mô tả công việc (JD)</label>
            <textarea id="studio-jd" required rows={6} maxLength={12000} value={jd} onChange={(event) => setJD(event.target.value)} />
            <label htmlFor="studio-template">Mẫu CV</label>
            <select id="studio-template" value={template} onChange={(event) => setTemplate(event.target.value as Template)}>
              <option value="classic">Cổ điển</option>
              <option value="technical">Kỹ thuật</option>
            </select>
            <label htmlFor="studio-source">CV đã xác nhận</label>
            <select id="studio-source" value={selectedCV} onChange={(event) => setSelectedCV(event.target.value)}>
              <option value="">Không chọn CV</option>
              {cvs.map((cv) => <option key={cv.id} value={cv.id}>
                CV #{cv.id} · {new Date(cv.uploaded_at).toLocaleDateString('vi-VN')}
              </option>)}
            </select>
            {nextCV && <Button onClick={loadOlderCVs}>Tải thêm CV</Button>}
            <label><input type="checkbox" checked={useGitHub} onChange={(event) => setUseGitHub(event.target.checked)} /> Dùng bằng chứng từ repo GitHub công khai</label>
            <label><input type="checkbox" checked={permission} onChange={(event) => setPermission(event.target.checked)} /> Cho phép AI nhận mã kỹ năng để chọn dữ kiện theo JD</label>
            <Button type="submit" disabled={!permission || (!selectedCV && !useGitHub) || !title.trim() || !jd.trim()}>Tạo bản nháp</Button>
          </fieldset>
        </form>
      </Card>
      <Card>
        <h2>CV đã lưu</h2>
        {!busy && !documents.length && <p>Trang này chưa có CV.</p>}
        <ul className="cv-studio-list">
          {documents.map((item) => <li key={item.document_id}>
            <Button disabled={busy} onClick={() => openVersion(item.document_id, item.number)}>
              {item.title} · bản {item.number}
            </Button>
          </li>)}
        </ul>
        <Pagination offset={documentsOffset} size={documents.length} busy={busy}
          onPage={(offset) => { void run((signal) => loadDocuments(offset, signal)) }} />
      </Card>
    </div>
    {detail && <Card>
      <h2>{detail.title} · bản {detail.number}</h2>
      <h3>Lịch sử phiên bản</h3>
      <div className="cv-studio-actions">
        {versions.map((version) => <Button key={version.number} disabled={busy || version.number === detail.number}
          onClick={() => openVersion(version.document_id, version.number)}>
          Bản {version.number}
        </Button>)}
      </div>
      <Pagination offset={versionsOffset} size={versions.length} busy={busy}
        onPage={(offset) => { void run((signal) => loadVersions(detail.document_id, offset, signal)) }} />
      {detail.source_unavailable && <p role="alert">Nguồn GitHub đã thay đổi. Hãy tạo bản nháp từ nguồn còn truy cập được để tiếp tục lưu và xuất.</p>}
      <h3>Nội dung đã lưu và nguồn</h3>
      <ul className="cv-studio-list">
        {detail.lines.map((line, index) => line.source.type !== 'missing' && line.text.trim() && <li key={index}>
          <p>{line.text}</p><small>{citation(line.source)}</small>
        </li>)}
      </ul>
      {missing.length > 0 && <>
        <h3>Dữ kiện cần bổ sung</h3>
        <ul>{missing.map((line) => <li key={line.text}>{line.text}</li>)}</ul>
      </>}
      {canEdit && <form onSubmit={(event) => { event.preventDefault(); save() }}>
        <fieldset disabled={busy}>
          <legend>Chỉnh sửa và lưu phiên bản mới</legend>
          <label htmlFor="studio-edit-title">Tên phiên bản</label>
          <input id="studio-edit-title" required maxLength={120} value={editTitle} onChange={(event) => setEditTitle(event.target.value)} />
          <label htmlFor="studio-edit-body">Nội dung</label>
          <textarea id="studio-edit-body" required rows={10} maxLength={20000} value={editText} onChange={(event) => setEditText(event.target.value)} />
          <Button type="submit" disabled={!dirty || !editTitle.trim() || !editText.trim()}>Lưu phiên bản mới</Button>
        </fieldset>
      </form>}
      <div className="cv-studio-actions">
        <Button disabled={busy || detail.source_unavailable || Boolean(dirty)} onClick={() => download('pdf')}>Xuất PDF</Button>
        <Button disabled={busy || detail.source_unavailable || Boolean(dirty)} onClick={() => download('docx')}>Xuất DOCX</Button>
      </div>
      {dirty && <p>Lưu chỉnh sửa để xuất nội dung mới.</p>}
    </Card>}
  </main>
}
