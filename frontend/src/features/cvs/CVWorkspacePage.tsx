import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { ApiError, apiFetch } from '@/shared/api/client'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import './cvWorkspace.css'

type CVListItem = { id: number; uploaded_at: string }
type SavedCV = CVListItem & { version: number; text: string }
type Preview = { receipt: string; text: string }
const FORMATS: Record<string, string> = {
  pdf: 'application/pdf',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.'
    if (error.status === 403) return 'Yêu cầu bị từ chối. Hãy mở lại trang từ địa chỉ chính của ứng dụng.'
    if (error.status === 404) return 'CV không còn khả dụng.'
    if (error.status === 409) return 'CV đã thay đổi. Hãy mở lại bản mới nhất.'
    if (error.status === 413) return 'Tệp vượt quá giới hạn 5 MB.'
    if (error.status === 415) return 'Tệp cần đúng định dạng PDF hoặc DOCX.'
    if (error.status === 429) return 'Đang có nhiều tệp được xử lý. Hãy thử lại.'
    if (error.status === 503) return 'Dịch vụ xử lý CV chưa sẵn sàng. Hãy thử lại.'
    if (error.status === 422 && typeof error.body === 'object' && error.body
      && 'detail' in error.body && typeof error.body.detail === 'string') return error.body.detail
    return error.message
  }
  return 'Không thể xử lý yêu cầu CV.'
}

export function CVWorkspacePage() {
  const { user, isLoading } = useAuth()
  if (isLoading) return <p role="status">Đang kiểm tra đăng nhập…</p>
  if (!user) return <p>Bạn cần đăng nhập để quản lý CV. <Link to="/">Về Dashboard</Link></p>
  return <Workspace key={user.id} />
}

function Workspace() {
  const [items, setItems] = useState<CVListItem[]>([])
  const [editor, setEditor] = useState<Preview | SavedCV>()
  const [text, setText] = useState('')
  const [file, setFile] = useState<File>()
  const [busy, setBusy] = useState(true)
  const [nextPage, setNextPage] = useState<number>()
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [remove, setRemove] = useState<number>()
  const session = useRef<AbortController | null>(null)
  const running = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    session.current = controller
    apiFetch<CVListItem[]>('/cvs', { signal: controller.signal })
      .then((list) => {
        if (controller.signal.aborted) return
        setItems(list)
        setNextPage(list.length === 50 ? list.at(-1)?.id : undefined)
      })
      .catch((err) => { if (!controller.signal.aborted) setError(errorMessage(err)) })
      .finally(() => { if (!controller.signal.aborted) setBusy(false) })
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

  function preview() {
    if (!file) return
    const format = FORMATS[file.name.split('.').at(-1)?.toLowerCase() ?? '']
    if (!format || !file.size || file.size > 5 * 1024 * 1024) {
      setError('Chọn một tệp PDF hoặc DOCX có dung lượng tối đa 5 MB.')
      return
    }
    void run(async (signal) => {
      const result = await apiFetch<Preview>('/cvs/preview', {
        method: 'POST',
        headers: { 'Content-Type': format },
        rawBody: file,
        signal,
        timeoutMs: 45_000,
      })
      if (signal.aborted) return
      setEditor(result)
      setText(result.text)
      setRemove(undefined)
    })
  }

  function loadMore() {
    if (nextPage === undefined) return
    void run(async (signal) => {
      const page = await apiFetch<CVListItem[]>(`/cvs?before_id=${nextPage}`, { signal })
      if (signal.aborted) return
      setItems((current) => [...current, ...page])
      setNextPage(page.length === 50 ? page.at(-1)?.id : undefined)
    })
  }

  function open(id: number) {
    void run(async (signal) => {
      const result = await apiFetch<SavedCV>(`/cvs/${id}`, { signal })
      if (signal.aborted) return
      setEditor(result)
      setText(result.text)
      setRemove(undefined)
    })
  }

  function save() {
    if (!editor || !text.trim()) return
    void run(async (signal) => {
      const result = 'receipt' in editor
        ? await apiFetch<SavedCV>('/cvs', { method: 'POST', body: { receipt: editor.receipt, text }, signal })
        : await apiFetch<SavedCV>(`/cvs/${editor.id}`, { method: 'PUT', body: { version: editor.version, text }, signal })
      if (signal.aborted) return
      setEditor(result)
      setText(result.text)
      setItems((old) => old.some((item) => item.id === result.id)
        ? old : [{ id: result.id, uploaded_at: result.uploaded_at }, ...old])
      setNotice('Đã lưu CV.')
    })
  }

  function deleteCV(id: number) {
    void run(async (signal) => {
      await apiFetch(`/cvs/${id}`, { method: 'DELETE', signal })
      if (signal.aborted) return
      if (editor && 'id' in editor && editor.id === id) {
        setEditor(undefined)
        setText('')
      }
      setItems((old) => old.filter((item) => item.id !== id))
      setRemove(undefined)
      setNotice('Đã xóa CV.')
    })
  }

  return (
    <main className="cv-workspace">
      <Link to="/dashboard">← Dashboard</Link>
      <h1>CV của tôi</h1>
      <div className="cv-actions">
        <Link to="/cv-studio">Tạo CV theo JD trong AI CV Studio</Link>
        <Link to="/cvs/references">Mẫu CV tham khảo</Link>
      </div>
      <Card>
        <fieldset disabled={busy}>
          <label htmlFor="cv-file">Tệp CV (PDF có văn bản hoặc DOCX, tối đa 5 MB)</label>
          <input id="cv-file" type="file" accept=".pdf,.docx" onChange={(event) => setFile(event.target.files?.[0])} />
          <Button onClick={preview} disabled={!file} variant="primary">Quét tệp và xem trước</Button>
        </fieldset>
      </Card>
      {busy && <p role="status">Đang xử lý…</p>}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {editor && (
        <Card>
          <fieldset disabled={busy}>
            <h2>{'receipt' in editor ? 'Xem trước CV' : `Chỉnh CV #${editor.id}`}</h2>
            <label htmlFor="cv-text">Văn bản CV</label>
            <textarea id="cv-text" value={text} rows={16} maxLength={50_000}
              onChange={(event) => setText(event.target.value)} />
            <div className="cv-actions">
              <Button variant="primary" onClick={save} disabled={!text.trim()}>
                {'receipt' in editor ? 'Xác nhận và lưu' : 'Lưu chỉnh sửa'}
              </Button>
              <Button onClick={() => { setEditor(undefined); setText('') }}>Đóng</Button>
            </div>
          </fieldset>
        </Card>
      )}
      <Card>
        <h2>CV đã tải lên</h2>
        {!busy && !items.length && <p>Chưa có CV đã xác nhận.</p>}
        <ul className="cv-items">
          {items.map((item) => (
            <li key={item.id}>
              <span>CV #{item.id} · {new Date(item.uploaded_at).toLocaleDateString('vi-VN')}</span>
              <div className="cv-actions">
                {remove === item.id ? (
                  <>
                    <Button disabled={busy} variant="danger" onClick={() => deleteCV(item.id)}>Xác nhận xóa</Button>
                    <Button disabled={busy} onClick={() => setRemove(undefined)}>Hủy</Button>
                  </>
                ) : (
                  <>
                    <Button disabled={busy} onClick={() => open(item.id)}>Mở CV</Button>
                    <Button disabled={busy} onClick={() => setRemove(item.id)}>Xóa</Button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
        {nextPage !== undefined && <Button disabled={busy} onClick={loadMore}>Xem thêm CV</Button>}
      </Card>
    </main>
  )
}
