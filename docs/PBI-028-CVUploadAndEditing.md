# PBI-028 — Tải lên, xem trước và chỉnh sửa CV

Mã T065DED · [Trello](https://trello.com/c/HfBAoPIk) · SRS 2.0 FR-023.

## Chạy tính năng

Từ gốc repo, chạy `docker compose up -d --build`. ClamAV cập nhật và lưu
cơ sở chữ ký qua volume `clamav_signatures`. Khi mới khởi động, có thể cần
chờ dịch vụ quét sẵn sàng. Nếu UI báo dịch vụ quét chưa sẵn sàng, xem
`docker compose logs --tail=80 clamav`. Compose giữ cổng ClamAV trong
mạng của dịch vụ backend và scanner. Không publish cổng scanner.

Nếu chạy backend ngoài Docker, cài dependency bằng `pip install ".[dev]"`
từ thư mục `backend`, chạy một clamd tin cậy và đặt
`CV_SCANNER_HOST`, `CV_SCANNER_PORT` trong môi trường backend.
Mã xác nhận được ký/mã hóa bằng khóa dẫn xuất riêng cho tính năng CV
từ `GITHUB_TOKEN_ENCRYPTION_KEY`.

## Sử dụng

1. Đăng nhập và mở **Dashboard → CV của tôi**.
2. Chọn PDF có văn bản hoặc DOCX, tối đa 5 MiB. Bấm **Quét tệp và xem trước**.
3. Rà lại và sửa nội dung rồi bấm **Xác nhận và lưu**. Mã xác nhận có hiệu
   lực 15 phút và gắn với tài khoản. Hệ thống chỉ trích xuất văn bản từ
   tệp và lưu nội dung bạn xác nhận. Luồng này không gửi CV cho AI.
4. Mở CV đã xác nhận để sửa tiếp hoặc xóa. Hai lượt sửa đồng thời bị
   kiểm tra phiên bản để tránh ghi đè lẫn nhau.

Văn bản PDF có thể mất bố cục, và PDF scan ảnh cần OCR bên ngoài trước khi tải.
DOCX trích xuất văn bản ở nội dung chính, kể cả đoạn nằm trong bảng.
Ứng dụng không lưu tệp gốc hoặc bản xem trước. Văn bản đã xác nhận
được lưu trong `ita.cvs.content`, dùng schema PostgreSQL hiện có.
Các CV tải lên đã xác nhận có thể được chọn làm nguồn bên Mentor theo
luồng người dùng chủ động chọn nguồn hiện có.

## API

- `POST /api/v1/cvs/preview` nhận bytes với Content-Type PDF hoặc DOCX. Backend
  kiểm tra giới hạn, định dạng, ClamAV và thời gian trích xuất trước khi trả
  `text` và `receipt`. Nếu scanner không trả kết quả tin cậy, upload bị từ chối.
- `POST /api/v1/cvs` xác nhận `receipt` và `text`. Gửi lại cùng mã trả CV
  đã lưu nếu CV đó vẫn tồn tại.
- `GET /api/v1/cvs` liệt kê tối đa 50 CV theo thứ tự mới nhất trước. Dùng
  `before_id` với ID cuối để lấy trang kế tiếp.
- `GET /api/v1/cvs/{id}` đọc CV. `PUT /api/v1/cvs/{id}` sửa `text` và yêu cầu
  `version` hiện tại. `DELETE /api/v1/cvs/{id}` xóa CV.
- Các API yêu cầu phiên đăng nhập. Mọi API ghi dữ liệu và upload kiểm tra Origin.
  Các API đọc/sửa/xóa lọc owner trước khi truy xuất nội dung. Nội dung CV,
  tệp và mã xác nhận không xuất hiện trong thông báo lỗi.

## Kiểm thử

Chạy Ruff, pytest và các check frontend như CI. Để chạy luồng CV với
PostgreSQL riêng, bật `RUN_INTEGRATION=1` và dùng tài khoản PostgreSQL có
quyền tạo DB tạm, rồi chạy `python -m pytest tests/modules/cvs`.
Các test dùng PDF/DOCX được tạo trong bộ test và mô phỏng verdict scanner
khi test điều kiện lỗi hoặc vòng đời CV. Chạy ứng dụng sử dụng ClamAV thật.
