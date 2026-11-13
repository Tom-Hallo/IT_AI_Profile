# AI Mentor đa nguồn (PBI-021)

Phạm vi của tài liệu là bộ chọn nguồn và câu trả lời có dẫn chứng theo SRS 2.0 FR-016.

- Đăng nhập rồi mở `/mentor` hoặc chọn **AI Mentor** trên trang trạng thái hệ thống.
- Chọn repository GitHub, CV đã lưu, roadmap của mình và/hoặc dán JD cho lượt hỏi.
  `GET /api/v1/mentor/sources` liệt kê CV và roadmap của tài khoản hiện tại.
  `POST /api/v1/mentor/chat` nhận `github_repo_ids`, `cv_ids`, `roadmap_ids` và `jd_text`
  trong `sources`. Client cũ có thể dùng `include_cv: true` để chọn tối đa ba CV mới nhất.
- Cấu hình `AI_PROVIDER` và `AI_MODEL` theo mẫu môi trường hiện có. Với OpenAI,
  thiết lập `AI_API_KEY` trong môi trường backend. Với Ollama, thiết lập `AI_BASE_URL`
  và cài model tương ứng. Khởi động lại backend sau khi đổi cấu hình.
- Với repo riêng tư, quyền GitHub và hai consent PBI-007 phải còn hiệu lực.
  Chỉ metadata bằng chứng của từng tệp nằm trong giao của hai phạm vi mới được gửi
  cho provider được chính sách cho phép. Cơ chế hiện tại hỗ trợ consent OpenAI.
  Repo công khai chỉ dùng báo cáo được tạo ở scope `public`, nếu có.
- Câu trả lời hiển thị ID trích dẫn, nguồn đã gửi và giới hạn. ID trích dẫn được
  đối chiếu với payload của lượt hỏi. Giá trị `confidence` để trống khi chưa có
  phương pháp hiệu chuẩn. Dữ liệu vượt ngân sách bị bỏ theo mục hoàn chỉnh.
