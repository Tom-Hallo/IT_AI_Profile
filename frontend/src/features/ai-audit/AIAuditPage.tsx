import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '@/features/auth/useAuth'
import { ApiError, apiFetch } from '@/shared/api/client'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import './aiAudit.css'

const labels = {
  feature: { mentor: 'AI Mentor', cv_studio: 'CV Studio', repository_ai: 'Phân tích bằng AI' },
  phase: { context: 'Truy xuất nguồn', provider: 'Gọi provider', tool: 'Công cụ' },
  source: {
    github: 'GitHub', github_public: 'GitHub công khai', github_private: 'GitHub riêng tư',
    cv: 'CV', jd: 'Mô tả công việc', roadmap: 'Lộ trình', chat: 'Câu hỏi trong chat',
  },
  provider: { openai: 'OpenAI', ollama: 'Ollama' },
  consent: {
    selected: 'Đã chọn nguồn', double_granted: 'Đủ hai bước đồng ý',
    policy_allowed: 'Được phép theo chính sách', denied: 'Bị chặn theo quyền hoặc consent',
    confirmed: 'Đã xác nhận', declined: 'Đã từ chối', not_requested: 'Chưa xác nhận',
  },
  status: {
    retrieved: 'Đã truy xuất', unavailable: 'Nguồn không khả dụng',
    started: 'Được phép gửi', succeeded: 'Thành công', denied: 'Bị chặn', failed: 'Lỗi',
    timeout: 'Hết thời gian chờ', cancelled: 'Đã hủy', skipped: 'Đã bỏ qua',
    proposed: 'Đã đề xuất', confirmed: 'Đã xác nhận', declined: 'Đã từ chối',
    expired: 'Đã hết hạn', queue_deferred: 'Đang chờ đưa vào hàng đợi',
  },
  tool: {
    create_cv: 'Tạo bản nháp CV', create_roadmap: 'Tạo lộ trình', reanalyze_repository: 'Phân tích lại repo',
  },
}

type LabelKey<T extends keyof typeof labels> = keyof (typeof labels)[T]
type AuditEvent = {
  id: string
  operation_id: string
  created_at: string
  feature: LabelKey<'feature'>
  phase: LabelKey<'phase'>
  source: LabelKey<'source'>
  provider: LabelKey<'provider'> | null
  consent: LabelKey<'consent'>
  status: LabelKey<'status'>
  tool: LabelKey<'tool'> | null
}
type AuditPage = { items: AuditEvent[]; next_before: string | null }
const dateFormat = new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'medium' })

export function AIAuditPage() {
  const { user, isLoading, error } = useAuth()
  if (isLoading) return <p role="status">Đang kiểm tra đăng nhập…</p>
  if (error) return <p role="alert">{error} <Link to="/dashboard">Về Dashboard</Link></p>
  if (!user) return <p>Bạn cần đăng nhập để xem lịch sử AI. <Link to="/dashboard">Về Dashboard</Link></p>
  return <AuditHistory key={user.id} />
}

function AuditHistory() {
  const [request, setRequest] = useState<{ before: string | null }>({ before: null })
  const [result, setResult] = useState<{ request: typeof request; page: AuditPage }>()
  const [error, setError] = useState<{ request: typeof request; message: string }>()
  const page = result?.request === request ? result.page : undefined
  const message = error?.request === request ? error.message : undefined

  useEffect(() => {
    const controller = new AbortController()
    const path = request.before ? `/ai-audit?before=${encodeURIComponent(request.before)}` : '/ai-audit'
    apiFetch<AuditPage>(path, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setResult({ request, page: data })
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError({ request, message: err instanceof ApiError && err.status === 401
          ? 'Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.'
          : 'Không tải được lịch sử AI. Hãy thử lại.' })
      })
    return () => controller.abort()
  }, [request])

  return <main className="ai-audit-page">
    <div className="pixel-page-heading">
      <span className="pixel-eyebrow">SECURITY / AI AUDIT LOG</span>
      <h1>Lịch sử sử dụng AI</h1>
      <p>Nhật ký kiểm toán truy vấn, chính sách đồng ý (consent) và các tác vụ AI.</p>
    </div>
    <nav aria-label="Điều hướng lịch sử AI">
      <Link to="/dashboard">Dashboard</Link>
      <Link to="/mentor">AI Mentor</Link>
    </nav>
    <h1>Lịch sử sử dụng AI</h1>
    {!page && !message && <p role="status">Đang tải sự kiện…</p>}
    {message && <>
      <p role="alert">{message}</p>
      <Button onClick={() => setRequest({ before: request.before })}>Thử lại</Button>
    </>}
    {page && <>
      <div className="ai-audit-actions">
        <Button onClick={() => setRequest({ before: null })}>
          {request.before ? 'Về sự kiện mới nhất' : 'Làm mới'}
        </Button>
        {page.next_before && <Button onClick={() => setRequest({ before: page.next_before })}>
          Sự kiện cũ hơn
        </Button>}
      </div>
      {page.items.length === 0 && <p role="status">Chưa có sự kiện sử dụng AI.</p>}
      <ol className="ai-audit-list">
        {page.items.map((event) => <li key={event.id}>
          <Card aria-label={`${labels.phase[event.phase]} · ${labels.source[event.source]}`}>
            <h2>{event.tool ? labels.tool[event.tool] : labels.phase[event.phase]}</h2>
            <p>
              <time dateTime={event.created_at}>{dateFormat.format(new Date(event.created_at))}</time>
              {' · '}{labels.feature[event.feature]}
            </p>
            <dl>
              <dt>{event.tool ? 'Đích công cụ' : 'Nguồn'}</dt><dd>{labels.source[event.source]}</dd>
              <dt>Provider</dt><dd>{event.provider ? labels.provider[event.provider] : 'Chưa ghi nhận'}</dd>
              <dt>Consent</dt><dd>{labels.consent[event.consent]}</dd>
              <dt>Trạng thái</dt><dd>{labels.status[event.status]}</dd>
            </dl>
          </Card>
        </li>)}
      </ol>
    </>}
  </main>
}
