import { useRef, useState } from 'react'
import { Button } from '@/shared/ui/Button'
import { decideMentorAction } from './api'
import type { MentorAction, MentorActionDecision, MentorActionResult } from './types'

const labels = {
  create_cv: 'Tạo bản nháp CV',
  create_roadmap: 'Tạo roadmap',
  reanalyze_repository: 'Phân tích lại repository',
}

const sourceLabels: Record<string, string> = {
  github: 'Dữ liệu GitHub công khai đã chọn',
  cv: 'CV đã chọn',
  jd: 'Mô tả công việc đã dán',
  roadmap: 'Roadmap đã chọn',
}

const messages: Record<MentorActionResult['status'], string> = {
  pending: 'Đang chờ xác nhận.',
  declined: 'Bạn đã từ chối hành động.',
  expired: 'Đề xuất đã hết hạn. Hãy yêu cầu AI tạo đề xuất mới.',
  succeeded: 'Hành động đã được thực hiện.',
  denied: 'Quyền truy cập hoặc sự đồng ý đã thay đổi.',
  failed: 'Không thể hoàn tất hành động. Hãy kiểm tra lại trước khi tạo đề xuất mới.',
}

export function MentorActionCard({
  action,
  onCompleted,
}: {
  action: MentorAction
  onCompleted: () => void
}) {
  const [result, setResult] = useState<MentorActionResult>()
  const [requestError, setRequestError] = useState(false)
  const [busy, setBusy] = useState(false)
  const lastDecision = useRef<MentorActionDecision>('confirm')
  const inFlight = useRef(false)
  const proposal = action.proposal

  async function decide(decision: MentorActionDecision) {
    if (inFlight.current) return
    inFlight.current = true
    lastDecision.current = decision
    setBusy(true)
    setRequestError(false)
    try {
      const response = await decideMentorAction(action.id, decision)
      setResult(response)
      if (response.status === 'succeeded') onCompleted()
    } catch {
      setRequestError(true)
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  return (
    <section className="mentor-action" aria-label={labels[action.tool]}>
      <h3>{labels[action.tool]}</h3>
      <p>Dữ liệu sử dụng: {action.sources.map((source) => sourceLabels[source] ?? source).join(', ')}</p>
      <p>Tác động: {action.impact}</p>
      {proposal.tool !== 'reanalyze_repository' && (
        <details>
          <summary>Xem nội dung sẽ lưu</summary>
          <p><strong>{proposal.title}</strong></p>
          {proposal.tool === 'create_cv' ? (
            <>
              <p>{proposal.summary}</p>
              <p>{proposal.skills.join(', ')}</p>
            </>
          ) : (
            <ol>{proposal.steps.map((step, index) => <li key={index}>{step}</li>)}</ol>
          )}
        </details>
      )}
      <p>Hết hạn lúc {new Date(action.expires_at).toLocaleTimeString('vi-VN')}.</p>
      {result && (
        <p role="status">
          {result.status === 'succeeded' && proposal.tool === 'reanalyze_repository'
            ? 'Đã lưu yêu cầu phân tích. Theo dõi tiến độ bằng mã job.'
            : messages[result.status]}{result.result_id ? ` Mã kết quả: ${result.result_id}` : ''}
        </p>
      )}
      {requestError && <p role="alert">Chưa nhận được kết quả. Bạn có thể gửi lại quyết định.</p>}
      <div className="mentor-action-buttons">
        {requestError ? (
          <Button type="button" disabled={busy} onClick={() => void decide(lastDecision.current)}>
            Kiểm tra lại
          </Button>
        ) : !result || result.status === 'pending' ? (
          <>
            <Button type="button" variant="primary" disabled={busy} onClick={() => void decide('confirm')}>
              Xác nhận
            </Button>
            <Button type="button" disabled={busy} onClick={() => void decide('decline')}>
              Từ chối
            </Button>
          </>
        ) : null}
      </div>
    </section>
  )
}
