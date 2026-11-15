# PBI-029 — AI CV Studio

Từ Dashboard, mở **AI CV Studio**. Nhập tên, dán JD và chọn mẫu **Cổ điển** hoặc **Kỹ thuật**. Chọn CV đã xác nhận ở **CV của tôi**, bật nguồn GitHub công khai đã phân tích, hoặc dùng cả hai. Xác nhận sử dụng AI rồi chọn **Tạo bản nháp**.

AI provider dùng cấu hình có sẵn của PBI-020. Model chỉ nhận mã kỹ năng chuẩn, mức yêu cầu của JD, loại nguồn và số thứ tự mục. Nội dung CV, JD nguyên văn và dữ liệu từ repository được xử lý trong backend. AI chỉ được chọn các mục có nguồn. GitHub dùng báo cáo công khai có bằng chứng đạt ngưỡng PBI-027. Nguồn CV là nội dung người dùng đã xác nhận qua PBI-028.

Bản nháp được lưu dưới bản 1. Nguồn CV ghi ID, số phiên bản và dòng. Nguồn GitHub ghi repo, commit và ID bằng chứng. Danh sách yêu cầu chưa có dữ kiện được hiển thị riêng. Hãy đối chiếu CV người dùng cung cấp và các dòng tự nhập trước khi gửi cho nhà tuyển dụng.

Sửa bản mới nhất rồi chọn **Lưu phiên bản mới**. Chọn từng bản trong lịch sử để xem lại và xuất PDF hoặc DOCX của bản đó. Tệp xuất chứa nội dung CV đã lưu. Cảnh báo thiếu dữ kiện và thẻ nguồn dùng để rà soát trong Studio. PDF nhúng font DejaVu Sans có hỗ trợ tiếng Việt. DOCX có thể tiếp tục sửa trong trình soạn thảo và hỗ trợ nội dung chứa ký tự ngoài phạm vi font PDF.

Khi hệ thống cập nhật trạng thái repo nguồn thành riêng tư hoặc người dùng ngắt kết nối GitHub, Studio ẩn dữ kiện đó và chặn lưu, xuất bản chứa dữ kiện đã mất quyền. CV Studio lưu bản chụp nội dung đã chọn, nên các phiên bản đã lưu vẫn giữ text gốc khi chỉnh sửa hay xóa hồ sơ tải lên.

## Chạy và kiểm tra

- Từ thư mục chứa Compose, chạy `docker compose up -d --build` để cài phụ thuộc xuất tệp và áp dụng migration.
- Kiểm tra `AI_PROVIDER`, `AI_MODEL` và `AI_BASE_URL` trong `.env`. Với OpenAI, đặt thêm `AI_API_KEY`. Với cấu hình Docker mặc định, tải model Ollama đã đặt trong `AI_MODEL` và chạy Ollama trên máy host.
- Backend dùng PostgreSQL test riêng. Tại `backend`, chạy `ruff check`, `ruff format --check` và `python -m pytest`. Bật `RUN_INTEGRATION=1` với PostgreSQL test và chạy `python -m pytest tests/modules/cv_studio` để kiểm tra luồng Studio.
- Tại `frontend`, chạy `npm ci`, `npm run lint` và `npm run build`.
