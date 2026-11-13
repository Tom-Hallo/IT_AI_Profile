# PBI-022 · AI Agent tool calling với xác nhận hành động

[Trello PBI-022](https://trello.com/c/g9j8qr1D) · SRS 2.0 M05, FR-017, UC-03, TC-017.
Phụ thuộc vào AI Mentor đa nguồn PBI-021. Tên branch và commit:

- `feature/T065DE8-PBI-022-AgentToolConfirmation`
- `T065DE8 : PBI-022-AgentToolConfirmation`

## Luồng sử dụng

1. Đăng nhập, vào **AI Mentor**, chọn nguồn phù hợp nếu có, rồi yêu cầu tạo CV,
   tạo roadmap hoặc phân tích lại repository đã chọn. Bấm **Đề xuất hành động**
   để bật các tool cho lượt này. Nút **Gửi** dùng chế độ hỏi đáp của PBI-021.
2. Thẻ đề xuất hiển thị dữ liệu sử dụng, tác động và thời hạn 5 phút. CV/roadmap
   có bản xem trước nội dung sẽ lưu. Đề xuất chưa tạo CV, roadmap hoặc job.
3. Bấm **Xác nhận** để lưu bản nháp hoặc tạo yêu cầu phân tích. Bấm **Từ chối**
   để kết thúc đề xuất. Gửi lại quyết định trên cùng mã sẽ nhận kết quả đã lưu.
4. CV và roadmap được lưu vào bảng hiện có theo tài khoản và hiện trong danh
   sách nguồn Mentor. Với phân tích lại, mã trả về là ID của job trong hệ
   thống phân tích. Tra tiến độ tại `GET /api/v1/analysis/jobs/{job_id}`.

Một số yêu cầu mẫu:

- “Tạo bản nháp CV từ CV tôi chọn, nhấn mạnh kinh nghiệm Python.”
- “Tạo roadmap học SQL và backend trong 4 tuần.”
- “Phân tích lại repository đã chọn.” Chọn repo trong Mentor trước khi gửi.

## API và bảo mật

- `POST /api/v1/mentor/chat` với `enable_actions: true` cho phép nhận đề xuất
  có cấu trúc. Allowlist gồm `create_cv`, `create_roadmap`,
  `reanalyze_repository`. Server kiểm tra kiểu, giới hạn và trường lạ trong
  tham số trước khi lưu. Client chỉ gửi mã đề xuất và lựa chọn.
- `POST /api/v1/agent/actions/{id}/approve` và `…/{id}/decline` yêu cầu
  phiên đăng nhập, Origin hợp lệ, đúng chủ sở hữu và đề xuất còn hạn.
- Server kiểm tra lại nguồn thuộc tài khoản khi lưu CV/roadmap. Để tránh
  giữ dữ liệu repo riêng tư trong bản nháp sau khi thu hồi consent, CV và
  roadmap chỉ được đề xuất từ lượt chat không chứa ngữ cảnh GitHub riêng tư.
- Agent chỉ được đề xuất phân tích repo xuất hiện trong ngữ cảnh GitHub
  đã được duyệt. Với repo riêng tư, bước chat dùng chính sách gửi ngữ cảnh
  hiện hành của PBI-021. Bước xác nhận và worker kiểm tra lại quyền GitHub
  và consent phân tích nội bộ.
- Khóa hàng PostgreSQL bảo vệ xác nhận đồng thời. Kết quả lưu CV/roadmap,
  bản ghi job và audit tương ứng được ghi trong giao dịch với quyết định.
  Job đã ghi có thể được dịch vụ maintenance phục hồi khi Redis tạm lỗi.
- Audit giữ mã hành động, người dùng, loại tool, trạng thái, thời điểm và mã
  kết quả. Payload chờ xác nhận ở trường riêng, bị xóa khi quyết định kết
  thúc hoặc khi maintenance quét hết hạn. Audit không chứa prompt, CV,
  tên repo, mã nguồn hay token.
- Production sử dụng provider, PostgreSQL và Redis/RQ thật. Test tự tạo
  database PostgreSQL riêng và dùng dữ liệu kiểm thử. Test xử lý phản hồi AI
  mô phỏng kết quả provider để kiểm soát các tình huống.

## Chạy và kiểm tra

Dùng thiết lập môi trường của dự án và chạy `python -m alembic upgrade head`
trong `backend` khi chạy ngoài Docker. Với Docker Compose, dùng dịch vụ
migration và maintenance có sẵn.

Trong `backend`:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest
$env:RUN_INTEGRATION = "1"
python -m pytest tests/modules/ai_mentor/test_agent_actions.py
Remove-Item Env:RUN_INTEGRATION
```

Các test tích hợp cần PostgreSQL có quyền tạo DB tạm và Redis dùng cho test.
Trong `frontend` chạy `npm ci`, `npm run typecheck`, `npm run lint` và
`npm run build`.
