# PBI-038 — Lịch sử sử dụng AI

Mở **Dashboard → Lịch sử sử dụng AI** hoặc đi từ **AI Mentor**. Mỗi sự kiện hiển thị thời điểm, chức năng, loại nguồn hoặc đích công cụ, provider, quyết định của người dùng hay chính sách và trạng thái. **Sự kiện cũ hơn** tải trang tiếp theo. **Làm mới** về trang mới nhất.

## Sự kiện và phạm vi

| Giai đoạn | Ý nghĩa |
| --- | --- |
| Truy xuất nguồn | Ghi loại dữ liệu được truy xuất, thiếu dữ liệu hoặc bị chặn trong AI Mentor, CV Studio và policy gateway của phân tích repo bằng AI. GitHub bị từ chối dùng nhãn chung để tránh suy đoán quyền hoặc trạng thái repo. |
| Gọi provider | Ghi từng lượt đã kiểm tra quyền và được phép gọi provider, rồi ghi kết quả cuối. Ghi cả timeout, lỗi và việc chặn lần thử lại sau khi quyền bị thu hồi. Truy xuất thành công chưa có nghĩa là nguồn được gửi đi. |
| Công cụ | Ghi đề xuất, xác nhận, từ chối, hết hạn, bị chặn và kết quả. Audit và thay đổi nghiệp vụ commit cùng nhau. Trạng thái chờ hàng đợi giữ nguyên cơ chế khôi phục của PBI-022. |

`started` cho biết backend đã duyệt lượt gửi. Sự kiện này được ghi bền vững ngay trước khi gọi provider. Thiếu audit ở bước đó sẽ chặn lần gọi. Nếu hệ thống ngắt sau khi bắt đầu hoặc không ghi được trạng thái cuối, dữ liệu đã ghi vẫn cho thấy lượt được duyệt mà chưa có kết quả cuối. Thông báo lỗi hạ tầng của audit chỉ ghi loại lỗi.

## Quyền truy cập và lưu trữ

- `GET /api/v1/ai-audit` dùng session đăng nhập, đọc theo chủ sở hữu và trả `Cache-Control: no-store`. Phân trang theo `before`, mặc định 30 và tối đa 100 sự kiện. Con trỏ do ứng dụng cấp và không thay đổi phạm vi quyền.
- Mỗi sự kiện chỉ chứa các nhãn trong danh sách cho phép, thời gian và mã tương quan. Không lưu prompt, phản hồi AI, source code, đường dẫn, ID repo/CV, token, secret, nội dung CV hay payload công cụ. Bảng cũ của PBI-020 vẫn phục vụ số liệu sử dụng và quota.
- Lịch sử bắt đầu từ khi áp dụng migration. Provider của công cụ cũ được hiển thị là **Chưa ghi nhận** khi thông tin đó chưa từng được thu thập. Khi xóa tài khoản, khóa ngoại xóa audit của tài khoản đó.
- FR-032 trong SRS 2.0 yêu cầu theo dõi metadata đã lược dữ liệu nhạy cảm. PBI-038 bổ sung luồng người dùng xem audit của chính mình theo checklist Trello.

## Chạy và kiểm tra

Từ thư mục gốc, chạy `docker compose up -d --build` để áp dụng migration. Đăng nhập, chọn nguồn JD trong AI Mentor và gửi câu hỏi. Mở lịch sử để thấy truy xuất JD, lượt gọi provider và kết quả. Các bài kiểm thử nghiệp vụ dùng PostgreSQL riêng và transport phản hồi AI giả lập để kiểm tra đúng từng trạng thái.

- Backend: tại `backend`, chạy `ruff check`, `ruff format --check` và `python -m pytest`. Bật `RUN_INTEGRATION=1` với PostgreSQL/Redis test để chạy kiểm tra quyền, consent và công cụ.
- Frontend: tại `frontend`, chạy `npm run lint` và `npm run build`.
