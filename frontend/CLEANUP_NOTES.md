# Frontend cleaned - IT Talent AI Profile
## Đã chỉnh
- Loại bỏ `node_modules`, `dist`, bản V9 gốc trùng lặp và ZIP lồng.
- Giữ nguyên toàn bộ mã nguồn React, API client, các module nghiệp vụ và các file HTML độc lập.
- Bổ sung route `/talent-os` vào React Router.
- Sửa lỗi mã hóa tiêu đề iframe.

## Chạy trên Windows
```powershell
cd frontend
npm ci
npm run typecheck
npm run lint
npm run build
npm run dev
```
Mở http://localhost:5173/talent-os

## Ghi chú
- V9 hiện vẫn chạy trong iframe từ `public/talent-os-v9/index.html`, chưa chuyển thành React components hoặc nối API thật.
- Các thư mục legacy `css`, `js`, `html`, `pbi024` và HTML ở gốc được giữ để tránh xóa nhầm chức năng.
- Trước khi thay thế thư mục frontend đang dùng, hãy sao lưu và kiểm tra `git status`.
- Chưa chạy được npm test/build trong môi trường tạo gói; hãy chạy các lệnh trên ở máy bạn.
