# IT Talent AI OS V10 — GitHub Live Code Rain

## Chạy

Từ thư mục gốc:

```bash
python -m http.server 5173
```

Mở http://localhost:5173/. Không mở bằng file://. Cần internet để tải Three.js từ CDN và GitHub API.

## Luồng

1. Nhập GitHub username và Enter.
2. GET `/users/{username}/repos?per_page=100&type=owner&sort=updated`.
3. Lọc repository public không fork, không archived.
4. Với tối đa 8 repository: Contents API đọc thư mục gốc và một thư mục src/app/lib/backend/frontend.
5. Chỉ lấy file code nhỏ hơn 45 KB; tối đa 8 snippets; hiển thị bằng textContent và link GitHub thật.

## Giới hạn có chủ đích

- Không lấy commit count, không tính score AI, không suy diễn kỹ năng.
- GitHub REST API không trả snippets từ endpoint `/repos`; cần request bổ sung.
- API public không xác thực có rate limit; trên trình duyệt, `download_url` có thể gặp lỗi CORS hoặc lỗi mạng. Giao diện giữ dữ liệu trước đó và thông báo lỗi.
- Chỉ quét một phần repository và tối đa 100 repo ở trang đầu, không phải tổng số repo của tài khoản.
- Không dùng token, không lưu mã nguồn vào localStorage.
- 84/100 và 24 repos trên giao diện là dữ liệu DEMO, không phải kết quả phân tích GitHub.
- Three.js vẫn là phần demo hiện có; chưa hợp nhất các WebGL renderer giữa các trang. Cần refactor vòng đời scene ở giai đoạn tiếp theo.
- OG image và og:url cần URL triển khai thực tế, không điền URL giả.
