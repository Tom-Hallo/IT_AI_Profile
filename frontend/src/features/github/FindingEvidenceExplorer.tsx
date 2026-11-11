import { useEffect, useState } from 'react'
import { fetchFindingDetail, fetchFindings } from './api'
import type { FindingDetail, FindingSummary } from './api'
import './FindingEvidenceExplorer.css'

interface Props { repositoryId: number; reportId?: number; commitSha: string }

export function FindingEvidenceExplorer({ repositoryId, reportId, commitSha }: Props) {
  const [findings, setFindings] = useState<FindingSummary[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<FindingDetail | null>(null)
  const [filter, setFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchFindings(repositoryId, reportId, controller.signal)
      .then((rows) => setFindings(rows))
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Không tải được findings')
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [repositoryId, reportId, commitSha])

  useEffect(() => {
    if (selectedId === null) return
    const controller = new AbortController()
    fetchFindingDetail(selectedId, controller.signal)
      .then((result) => {
        if (result.repository_id !== repositoryId || (reportId !== undefined && result.report_id !== reportId) || result.commit_sha !== commitSha) {
          setError('Finding không thuộc báo cáo đang xem')
          return
        }
        setDetail(result)
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Không tải được evidence')
      })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false) })
    return () => controller.abort()
  }, [selectedId, repositoryId, reportId, commitSha])

  const types = [...new Set(findings.map((f) => f.finding_type))]
  const visible = findings.filter((f) => filter === 'all' || f.finding_type === filter)
  return (
    <section className="finding-explorer card" aria-label="Truy vết Finding đến Evidence">
      <div className="finding-heading">
        <div>
          <h3>Finding → Evidence</h3>
          <p>Chọn kết luận để xem bằng chứng theo file và commit. Nội dung mã nguồn riêng tư không được hiển thị.</p>
        </div>
        <span>{findings.length} findings</span>
      </div>
      <div className="finding-filters" aria-label="Lọc loại finding">
        {['all', ...types].map((type) => <button type="button" key={type} aria-pressed={filter === type} onClick={() => setFilter(type)}>{type === 'all' ? 'Tất cả' : type}</button>)}
      </div>
      {loading && <p role="status">Đang tải findings…</p>}
      {error && <p role="alert" className="finding-error">{error}</p>}
      {!loading && !error && findings.length === 0 && <p>Chưa có Finding cho báo cáo này. Báo cáo cũ có thể cần chạy phân tích lại.</p>}
      <div className="finding-layout">
        <div className="finding-list" aria-label="Danh sách findings">
          {visible.map((finding) => <button key={finding.id} type="button" className="finding-item" aria-pressed={selectedId === finding.id} onClick={() => { setSelectedId(finding.id); setDetail(null); setError(null); setDetailLoading(true) }}>
            <strong>{finding.classification}</strong><span>{finding.finding_type} · {(finding.confidence_score * 100).toFixed(0)}% tin cậy</span>
          </button>)}
        </div>
        <div className="finding-detail" aria-live="polite">
          {selectedId === null && <p>Chọn một finding để xem nguồn bằng chứng.</p>}
          {detailLoading && <p role="status">Đang tải chi tiết…</p>}
          {detail && <>
            <h4>{detail.classification}</h4>
            <p>{detail.rationale}</p>
            <p><strong>Phiên bản bộ phân tích:</strong> {detail.analyzer_version}</p>
            <p><strong>Commit:</strong> <code>{detail.commit_sha}</code></p>
            <h5>Bằng chứng ({detail.evidence.length})</h5>
            {detail.evidence.length === 0 && <p>Chưa có bằng chứng liên kết.</p>}
            <ul>{detail.evidence.map((ev) => <li key={ev.id}>
              <code>{ev.file_path}{ev.line_number != null ? `:${ev.line_number}` : ''}</code>
              <span>{ev.evidence_source} · {ev.detection_method} · {(ev.confidence_score * 100).toFixed(0)}%</span>
              <small>Commit: {ev.commit_sha}</small>
            </li>)}</ul>
          </>}
        </div>
      </div>
    </section>
  )
}
