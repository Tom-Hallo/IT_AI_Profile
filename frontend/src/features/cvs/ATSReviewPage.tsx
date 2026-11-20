import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { apiFetch } from '@/shared/api/client'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'

type SavedCV = { id: number; uploaded_at: string }
type Review = {
  cv_version: number
  readability_score: number
  keyword_coverage: number | null
  keyword_matches: { keyword: string; found: boolean; evidence: string | null }[]
  suggestions: { type: string; message: string; evidence: string }[]
  layout_issues: { section: string; message: string }[]
  disclaimer: string
}

export function ATSReviewPage() {
  const { user, isLoading } = useAuth()
  if (isLoading) return <p role="status">Đang xác thực…</p>
  if (!user) return <p>Đăng nhập bằng GitHub để kiểm tra CV.</p>
  return <ReviewWorkspace key={user.id} />
}

function ReviewWorkspace() {
  const [items, setItems] = useState<SavedCV[]>([])
  const [cv, setCV] = useState('')
  const [jd, setJD] = useState('')
  const [result, setResult] = useState<Review>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    apiFetch<SavedCV[]>('/cvs', { signal: controller.signal })
      .then(list => {
        if (!controller.signal.aborted) { setItems(list); setCV(String(list[0]?.id ?? '')) }
      })
      .catch(err => { if (!controller.signal.aborted) setError(err.message) })
    return () => controller.abort()
  }, [])

  async function review() {
    setBusy(true)
    setError('')
    setResult(undefined)
    try {
      setResult(await apiFetch<Review>('/ats-reviews/preview', {
        method: 'POST', body: { cv_id: Number(cv), jd_text: jd.trim() || null },
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể phân tích CV.')
    } finally {
      setBusy(false)
    }
  }

  return <section className="job-matching">
    <div className="pixel-page-heading">
      <span className="pixel-eyebrow">CV / ATS REVIEW</span>
      <h1>Phản hồi ATS</h1>
      <p>Phân tích cấu trúc CV, độ phủ từ khóa và đề xuất cải thiện dựa trên JD.</p>
    </div>
    <Card>
      <p><Link to="/cvs">Tải lên hoặc chỉnh sửa CV</Link></p>
      <form onSubmit={event => { event.preventDefault(); if (cv && !busy) void review() }}>
        <fieldset disabled={busy}>
          <label htmlFor="ats-cv">CV đã lưu</label>
          <select id="ats-cv" value={cv} onChange={event => { setCV(event.target.value); setResult(undefined) }}>
            {!items.length && <option value="">Chưa có CV đã lưu</option>}
            {items.map(item => <option key={item.id} value={item.id}>CV #{item.id} · {new Date(item.uploaded_at).toLocaleDateString('vi-VN')}</option>)}
          </select>
          <label htmlFor="ats-jd">Mô tả công việc (tùy chọn)</label>
          <textarea id="ats-jd" rows={6} maxLength={20000} value={jd}
            onChange={event => { setJD(event.target.value); setResult(undefined) }} />
          <Button type="submit" disabled={!cv || busy}>{busy ? 'Đang kiểm tra…' : 'Kiểm tra ATS'}</Button>
        </fieldset>
      </form>
      {error && <p role="alert">{error}</p>}
    </Card>
    {result && <Card>
      <h2>Kết quả kiểm tra CV phiên bản {result.cv_version}</h2>
      <p>Điểm cấu trúc văn bản {result.readability_score}/100. Kiểm tra này dùng văn bản đã trích xuất từ CV.</p>
      <p>{result.keyword_coverage === null ? 'Chưa có từ khóa JD để đối chiếu.' : `Độ phủ từ khóa JD ${result.keyword_coverage}%`}</p>
      {!!result.keyword_matches.length && <ul>{result.keyword_matches.map(item => <li key={item.keyword}>
        <strong>{item.keyword}</strong> · {item.found ? 'Có trong CV' : 'Chưa có trong CV'}
        {item.evidence && <blockquote>{item.evidence}</blockquote>}
      </li>)}</ul>}
      {!!result.layout_issues.length && <ul>{result.layout_issues.map(issue => <li key={issue.section}>{issue.message}</li>)}</ul>}
      {!!result.suggestions.length && <ul>{result.suggestions.map(item => <li key={item.message}>{item.message}</li>)}</ul>}
      <p>{result.disclaimer}</p>
    </Card>}
  </section>
}
