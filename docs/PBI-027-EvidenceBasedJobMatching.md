# PBI-027 — Đối chiếu kỹ năng với JD

Mã task T065DEC. [Trello](https://trello.com/c/d69ozlWL) · SRS 2.0 FR-022.

## Sử dụng

Đăng nhập rồi mở **Dashboard → Đối chiếu kỹ năng với JD**. Dán JD và bấm
**Trích xuất kỹ năng**. Rà lại danh sách bắt buộc/ưu tiên, chọn phạm vi dữ liệu
và bấm **Đối chiếu kỹ năng**. Bạn cũng có thể nhập trực tiếp danh sách kỹ năng.
Nếu chưa có assessment, hãy chạy phân tích mã nguồn và xác minh đóng góp trước.
Với báo cáo công khai, chọn phạm vi **Public** khi phân tích.

## Dữ liệu và cách tính

- UI dùng `POST /api/v1/jobs/analyze` của PBI-025 để trích xuất từ văn bản.
  `POST /api/v1/jobs/match` nhận `scope` và `skills`, mỗi skill gồm
  `skill_key` và `level` (required/preferred). Backend lấy assessment có thật
  qua nguồn scoped skill snapshot của PBI-018.
- Một kỹ năng là **matched** khi có bằng chứng, điểm ≥ 70/100 và confidence
  ≥ 60/100. **Partial** có bằng chứng nhưng thấp hơn ít nhất một ngưỡng.
  **Unknown** nghĩa là thiếu assessment có bằng chứng, không suy ra người dùng
  thiếu kỹ năng. Nếu có nhiều assessment, ưu tiên bản đạt ngưỡng rồi xếp theo
  confidence và điểm. Ưu tiên required khi một kỹ năng có mặt ở cả hai nhóm.
- Tỷ lệ là số kỹ năng bắt buộc đạt ngưỡng chia cho tổng số kỹ năng bắt buộc.
  Khi toàn bộ kỹ năng bắt buộc là unknown hoặc danh sách không có kỹ năng
  bắt buộc, tỷ lệ để trống. Đây không phải xác suất tuyển dụng.
- Server kiểm tra phiên, Origin, quyền liên kết repo và consent private.
  Kết hợp hai phạm vi theo từng kỹ năng. Public chỉ dùng report/evidence
  có nhãn public rõ ràng. Report legacy all/full có thể đến từ repo từng
  private, nên bị loại khỏi phạm vi public. Private nhận private/all/full
  của repo hiện vẫn private và đã được cấp quyền.
- Báo cáo cũ hơn 90 ngày được đánh dấu. Tối đa 50 repo có report mỗi phạm vi,
  theo ngày phân tích. API trả tham chiếu evidence, không trả trích đoạn mã
  hoặc nội dung rationale. Kết quả tính theo yêu cầu, không cần migration.

## Kiểm tra

Trong backend, chạy Ruff và pytest như CI. Với PostgreSQL test riêng và tài
khoản có quyền CREATEDB, bật `RUN_INTEGRATION=1` rồi chạy:

```text
python -m pytest tests/modules/jobs/test_job_matching.py tests/modules/role_scoring/test_scoped_postgres.py
```

Trong frontend, chạy `npm run typecheck`, `npm run lint` và `npm run build`.
