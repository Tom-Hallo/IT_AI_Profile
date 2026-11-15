# PBI-031 — Mẫu CV tham khảo công khai

Mở **Dashboard → Mẫu CV tham khảo**, nhập tên công ty và vị trí rồi chọn **Tìm mẫu CV**. Bạn cũng có thể mở từ **CV của tôi** hoặc **Đối chiếu kỹ năng với JD**. Thử `Microsoft` với `Backend Developer` hoặc `Google` với `Data Engineer`.

Ứng dụng hiển thị link gốc, tác giả hoặc nhà xuất bản, giấy phép áp dụng cho mẫu và ngày đối chiếu. Dùng các gợi ý để chọn bố cục và cách trình bày. Hãy viết CV bằng dữ kiện của bạn. Nếu tái sử dụng phần được cấp phép, thực hiện điều kiện ghi công hoặc giữ thông báo giấy phép tương ứng.

## Tiêu chí tìm kiếm và xác minh

- `GET /api/v1/cvs/references?company=...&role=...` yêu cầu session đăng nhập. Hai tham số là tên công ty và chức danh, mỗi trường tối đa 120 ký tự. Backend xếp mẫu theo nhóm chức danh, có hỗ trợ từ đồng nghĩa tiếng Anh và tiếng Việt.
- `verified` yêu cầu một nguồn có quyền sử dụng cùng bằng chứng công khai xác nhận **cùng CV, công ty, vị trí và giai đoạn**. Giai đoạn có thể là qua vòng hồ sơ, được mời phỏng vấn hoặc nhận lời mời làm việc. Giấy phép, số lượt xem và lời tự kể không đủ để xác minh kết quả.
- Khi thiếu bằng chứng, API chỉ trả mẫu chung liên quan với nhãn `unverified`, hoặc trả danh sách rỗng khi chưa có mẫu cho chức danh. Danh mục ban đầu gồm năm nguồn mẫu và chưa có hồ sơ ứng tuyển được xác minh.
- Backend tra danh mục do nhóm duyệt trong `backend/app/modules/cvs/reference_catalog.py`. Nguồn ngoài danh sách bị bỏ qua. API không tải URL, không lưu nội dung CV nguồn, không phân tích CV riêng tư và không gửi thông tin truy vấn đến AI hay trang nguồn. Liên kết gốc chỉ được mở khi người dùng bấm.

## Cập nhật danh mục

Thêm nguồn qua PR sau khi đối chiếu trang gốc và điều kiện tái sử dụng áp dụng đúng cho mẫu. Lưu tên nhà xuất bản, link gốc, link căn cứ và ngày kiểm tra. Loại mục đã đổi quyền hoặc gỡ công khai. Với một kết quả được xác minh, kiểm tra bằng chứng từ công ty hoặc nguồn độc lập đáng tin cậy cho đúng CV, vị trí và giai đoạn trước khi thêm vào danh mục. Chỉ lưu link bằng chứng công khai; tránh thông tin liên hệ cá nhân và tài liệu tuyển dụng riêng tư.

## Kiểm tra

- SRS 2.0 FR-026 và TC-CV-01 quy định truy xuất nguồn được phép, truy vết và mẫu chung khi thiếu kết quả xác minh.
- Backend `ruff check`, `ruff format --check` và `python -m pytest tests/modules/cvs`. Bật `RUN_INTEGRATION=1` với PostgreSQL test riêng và Redis để kiểm tra session, phạm vi chủ sở hữu và hồi quy upload.
- Frontend `npm run lint` và `npm run build`. Tra lần lượt vị trí Backend, Data và một chức danh ngoài danh mục để kiểm tra trạng thái có mẫu, fallback và rỗng.
