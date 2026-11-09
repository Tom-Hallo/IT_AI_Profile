import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router'
import { apiFetch, ApiError } from '@/shared/api/client'

type Mode = 'preset' | 'month' | 'custom'
interface Analysis {
  period: { start_utc: string; end_exclusive_utc: string }
  activity: { commits: number; pull_requests_created: number; additions: number; deletions: number }
  base_code: { status: string; lines: number | null }
  limitations: string[]
}
export function ActivityAnalysisPage() {
  const { repositoryId } = useParams()
  const [mode, setMode] = useState<Mode>('preset')
  const [preset, setPreset] = useState('1m')
  const [month, setMonth] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [timezone, setTimezone] = useState('Asia/Ho_Chi_Minh')
  const [data, setData] = useState<Analysis | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError('')
    setData(null)
    if (!repositoryId || !/^\d+$/.test(repositoryId)) {
      setError('Repository ID không hợp lệ')
      return
    }
    const query = new URLSearchParams({ mode, timezone })
    if (mode === 'preset') query.set('preset', preset)
    if (mode === 'month') query.set('month', month)
    if (mode === 'custom') {
      query.set('start_date', start)
      query.set('end_date', end)
    }
    setLoading(true)
    try {
      setData(await apiFetch<Analysis>(
        `/repositories/${repositoryId}/activity/analysis?${query.toString()}`
      ))
    } catch (err) {
      const status = err instanceof ApiError ? err.status : undefined
      const messages: Record<number, string> = {
        401: 'Bạn cần đăng nhập GitHub.', 403: 'Không có quyền truy cập.',
        404: 'Không tìm thấy repository.', 409: 'Hãy đồng bộ GitHub trước.',
        413: 'Quá nhiều dữ liệu, hãy chọn kỳ ngắn hơn.',
        422: 'Tham số thời gian không hợp lệ.', 429: 'GitHub đang giới hạn truy cập.',
        500: 'Backend gặp lỗi.', 502: 'GitHub API gặp lỗi.',
      }
      setError(messages[status ?? 0] ?? 'Không thể tải dữ liệu.')
    } finally {
      setLoading(false)
    }
  }
  return <main style={{ maxWidth: 880, margin: '2rem auto', padding: '1rem' }}>
    <Link to="/">← Quay lại</Link>
    <h1>Phân tích hoạt động repository #{repositoryId}</h1>
    <form onSubmit={(e) => void submit(e)} style={{ display: 'grid', gap: 12 }}>
      <label>Chế độ <select value={mode} onChange={e => setMode(e.target.value as Mode)}>
        <option value="preset">Gần đây</option><option value="month">Theo tháng</option>
        <option value="custom">Tùy chọn</option>
      </select></label>
      {mode === 'preset' && <label>Khoảng <select value={preset} onChange={e => setPreset(e.target.value)}>
        <option value="1m">1 tháng</option><option value="3m">3 tháng</option>
        <option value="6m">6 tháng</option><option value="1y">1 năm</option>
      </select></label>}
      {mode === 'month' && <label>Tháng <input type="month" required value={month}
        onChange={e => setMonth(e.target.value)} /></label>}
      {mode === 'custom' && <>
        <label>Từ ngày <input type="date" required value={start}
          onChange={e => setStart(e.target.value)} /></label>
        <label>Đến ngày <input type="date" required min={start} value={end}
          onChange={e => setEnd(e.target.value)} /></label>
      </>}
      <label>Múi giờ <select value={timezone} onChange={e => setTimezone(e.target.value)}>
        <option value="Asia/Ho_Chi_Minh">Việt Nam (UTC+7)</option>
        <option value="UTC">UTC</option>
        <option value="America/New_York">New York</option>
      </select></label>
      <button type="submit" disabled={loading}>{loading ? 'Đang tải...' : 'Phân tích'}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {data && <section aria-live="polite">
      <h2>Kết quả</h2>
      <p>UTC: {data.period.start_utc} → {data.period.end_exclusive_utc} (không gồm mốc cuối)</p>
      <p>Commits: {data.activity.commits}</p>
      <p>PR tạo mới: {data.activity.pull_requests_created}</p>
      <p>Thêm/xóa dòng: {data.activity.additions} / {data.activity.deletions}</p>
      <p>Code nền: {data.base_code.status === 'available'
        ? data.base_code.lines : 'Chưa có snapshot lịch sử'}</p>
      <ul>{data.limitations.map(item => <li key={item}>{item}</li>)}</ul>
    </section>}
  </main>
}
