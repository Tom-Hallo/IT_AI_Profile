# Frontend — IT Talent AI Profile

Nền tảng frontend của dự án: **React + TypeScript + Vite**.
Phạm vi PBI-001: khung ứng dụng và một trang kiểm tra hệ thống. Chưa có giao diện nghiệp vụ,
đăng nhập GitHub hay dashboard phân tích.

## Yêu cầu

| Công cụ | Phiên bản |
|---|---|
| Node.js | **24 (LTS)** theo Technical Blueprint. Tối thiểu `22.22.0` (khai báo trong `package.json`) |
| npm | đi kèm Node.js |
| Docker + Docker Compose | chỉ cần khi chạy cả hệ thống bằng Compose |

Kiểm tra: `node -v` và `npm -v`.

## Cách 1 — Chạy cả hệ thống bằng Docker Compose (cách chuẩn của nhóm)

Thực hiện ở **thư mục gốc** repo (không phải trong `frontend/`), sau khi DevOps đã bàn giao `docker-compose.yml` và script setup:

```bash
./scripts/setup.sh              # Linux/macOS
.\scripts\setup.ps1             # Windows PowerShell
```

Mở <http://localhost:5173>. Dừng: `docker compose down`.

> Trạng thái hiện tại: Dockerfile của frontend đã có nhưng **chưa được build thử** trong môi trường
> phát triển của task này (không có Docker). Xem mục "Kiểm thử" bên dưới.

## Cách 2 — Chạy frontend riêng trên máy (không dùng Docker)

Từ thư mục `frontend/`:

```bash
# 1. Cài thư viện theo đúng package-lock.json
npm ci

# 2. Tạo file môi trường (file .env không được commit)
cp .env.example .env            # Linux/macOS
Copy-Item .env.example .env     # Windows PowerShell

# 3. Chạy chế độ phát triển (hot-reload)
npm run dev
```

Mở <http://localhost:5173>.

Nếu Backend chưa chạy, trang sẽ hiển thị lỗi "Không kết nối được tới Backend". Đó là hành vi đúng.
Backend chạy ở `http://127.0.0.1:8000` (xem `BACKEND_INTERNAL_URL` trong `.env`).

## Các lệnh

| Lệnh | Tác dụng |
|---|---|
| `npm run dev` | Chạy dev server ở cổng 5173 (có proxy `/api` tới Backend) |
| `npm run build` | Kiểm tra kiểu TypeScript rồi build production vào `dist/` |
| `npm run preview` | Chạy thử bản build (cùng cổng 5173, cùng proxy). Cần chạy `npm run build` trước |
| `npm run typecheck` | Chỉ kiểm tra kiểu TypeScript |
| `npm run lint` | Chạy ESLint |

## Biến môi trường

Nguồn chuẩn khi dùng Docker là file `.env.example` ở **thư mục gốc**. File `frontend/.env.example` chỉ dùng khi chạy ngoài Docker.

| Biến | Giá trị mặc định | Ý nghĩa |
|---|---|---|
| `VITE_API_BASE_URL` | `/api/v1` | Địa chỉ API mà trình duyệt gọi. **Bắt buộc.** Thiếu hoặc sai thì trang báo lỗi cấu hình. Biến `VITE_*` bị lộ ra trình duyệt nên **không đặt secret** |
| `BACKEND_INTERNAL_URL` | `http://127.0.0.1:8000` (ngoài Docker), `http://backend:8000` (Compose) | Nơi proxy của Vite chuyển tiếp `/api/*` tới. Chỉ dùng phía Node, không vào bundle |
| `FRONTEND_WATCH_POLLING` | `false` | Đặt `true` nếu hot-reload không chạy (thường gặp khi mount thư mục từ ổ Windows vào Docker) |

Lưu ý khi chạy ngoài Docker: dùng `127.0.0.1` thay vì `localhost` cho `BACKEND_INTERNAL_URL` để tránh lỗi phân giải IPv6.
Đổi giá trị trong `.env` thì phải khởi động lại `npm run dev`.

## Frontend gọi Backend như thế nào

```text
Trình duyệt ── /api/v1/health ──▶ Vite (cổng 5173) ── proxy ──▶ Backend (cổng 8000)
```

- Trình duyệt chỉ gọi **cùng origin** (`/api/v1/...`), nên không cần CORS và không lộ địa chỉ Backend.
- Mọi lời gọi API đi qua `apiFetch` trong `src/shared/api/client.ts`.
- Trang `/` chỉ gọi **một** endpoint đã chốt trong Blueprint: `GET /api/v1/health`.
  Frontend không tự tạo endpoint nào.

### Các trạng thái trang kiểm tra hệ thống

| Tình huống | Giao diện hiển thị |
|---|---|
| Backend khỏe (HTTP 200) | "Hoạt động", Database và Redis "Bình thường" |
| Backend sống nhưng dependency lỗi (HTTP 503 có `checks`) | Cảnh báo vàng, dòng bị lỗi ghi "Lỗi" |
| Backend tắt (proxy trả 502/504) hoặc không nối được | "Không kết nối được tới Backend" kèm hướng dẫn kiểm tra |
| Backend không trả lời trong 8 giây | "Backend không phản hồi kịp thời" |
| Backend trả lỗi HTTP khác (ví dụ 500) | "Backend trả lỗi HTTP 500" (không hiển thị nội dung lỗi thô) |
| Dữ liệu trả về sai định dạng | "Backend trả dữ liệu không đúng định dạng" |
| Thiếu `VITE_API_BASE_URL` | "Thiếu hoặc sai cấu hình địa chỉ API" (không gọi mạng) |

## Cấu trúc thư mục

```text
frontend/
├── Dockerfile              Image dev (node:24-alpine)
├── .dockerignore
├── .env.example            Biến môi trường mẫu (chỉ khi chạy ngoài Docker)
├── index.html
├── package.json            Dependency ghim phiên bản chính xác
├── package-lock.json
├── vite.config.ts          Cổng 5173, proxy /api, alias @/
├── tsconfig*.json          TypeScript strict
├── eslint.config.js
└── src/
    ├── main.tsx
    ├── vite-env.d.ts
    ├── app/                App.tsx, router.tsx, providers.tsx, NotFoundPage.tsx
    ├── shared/
    │   ├── config/env.ts   Đọc VITE_API_BASE_URL
    │   └── api/client.ts   apiFetch, ApiError, timeout
    ├── features/system-status/   Trang kiểm tra hệ thống + gọi /health
    └── styles/global.css
```

Quy ước: component `PascalCase.tsx`, hook `useXxx.ts`, file khác `camelCase.ts`, thư mục `kebab-case`,
alias import `@/` trỏ tới `src/`.

## Kiểm thử

Kiểm thử tự động (chạy được ở bất cứ máy nào có Node):

```bash
npm run typecheck      # kiểm tra kiểu TypeScript
npm run lint           # ESLint
npm run build          # typecheck + build production
```

Kiểm thử thủ công với Backend thật (sau khi Backend và Docker Compose đã bàn giao):

1. Chạy hệ thống, mở <http://localhost:5173> → thấy "Hoạt động", Database/Redis "Bình thường".
2. `docker compose stop backend`, bấm "Kiểm tra lại" → thấy "Không kết nối được tới Backend".
3. `docker compose start backend`, bấm "Kiểm tra lại" → trở lại "Hoạt động".
4. `docker compose stop postgres`, bấm "Kiểm tra lại" → thấy cảnh báo, Database "Lỗi".

## Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `Port 5173 is already in use` | Cổng bị chiếm. Tắt tiến trình đang dùng cổng đó. Cổng được cố định có chủ đích để không lệch với Compose; ở Docker, đổi cổng host bằng `FRONTEND_PORT` trong `.env` gốc |
| Trang báo "Thiếu hoặc sai cấu hình địa chỉ API" | Chưa có `frontend/.env` (xem Cách 2, bước 2) hoặc `VITE_API_BASE_URL` sai. Khởi động lại `npm run dev` |
| Trang báo "Không kết nối được tới Backend" | Backend chưa chạy hoặc `BACKEND_INTERNAL_URL` sai |
| Sửa code không tự cập nhật trong Docker trên Windows | Đặt `FRONTEND_WATCH_POLLING=true`, hoặc clone repo trong WSL2 |
| `npm ci` báo sai phiên bản Node | Cập nhật Node theo mục "Yêu cầu" |

## Ngoài phạm vi PBI-001

Đăng nhập GitHub, dashboard, thư viện UI, quản lý state toàn cục, React Query, Vitest, Dockerfile production.
