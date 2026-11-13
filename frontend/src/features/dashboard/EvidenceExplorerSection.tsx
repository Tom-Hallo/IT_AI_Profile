import { useState } from 'react'
import { Card } from '@/shared/ui/Card'
import { Button } from '@/shared/ui/Button'
import { Link } from 'react-router'

/**
 * Section dẫn người dùng sang Evidence Explorer thật.
 * Sẽ mở rộng thành interactive explorer đầy đủ ở bước tiếp theo.
 */
export function EvidenceExplorerSection() {
  const [showHelp, setShowHelp] = useState(false)

  return (
    <section className="dashboard-section">
      <h2>Evidence Explorer</h2>
      <Card>
        <p>
          Xem bằng chứng (evidence) gắn với từng finding: file path, commit SHA,
          confidence, detection method. Chỉ hiển thị dữ liệu bạn có quyền.
        </p>
        <div className="evidence-actions">
          <Link to="/analysis">
            <Button variant="primary">Mở phân tích Repository & Evidence</Button>
          </Link>
          <Button variant="ghost" onClick={() => setShowHelp((v) => !v)}>
            {showHelp ? 'Ẩn hướng dẫn' : 'Cách dùng Evidence'}
          </Button>
        </div>
        {showHelp && (
          <div className="evidence-help">
            <ol>
              <li>Vào trang Phân tích Repository.</li>
              <li>Chọn repository đã được phân tích.</li>
              <li>Trong báo cáo, dùng Finding → Evidence để xem chi tiết bằng chứng.</li>
              <li>Chỉ những repo bạn có quyền và đã consent mới hiển thị đầy đủ.</li>
            </ol>
          </div>
        )}
      </Card>
    </section>
  )
}