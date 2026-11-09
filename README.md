# IT Talent AI Profile

**IT Talent AI Profile** là dự án nền tảng hồ sơ năng lực CNTT thông minh dành cho **developer**. Định hướng của sản phẩm là kết nối GitHub, phân tích dự án và kỹ năng, hỗ trợ định hướng nghề nghiệp bằng AI, xây dựng lộ trình học tập và chuẩn bị CV phù hợp với vị trí ứng tuyển.

> **Trạng thái hiện tại (PBI-001, PBI-005):** Repository đã có nền tảng React/Vite, FastAPI, PostgreSQL, Redis và RQ Worker, cùng trang **kiểm tra trạng thái hệ thống**. PBI-005 bổ sung chức năng đăng nhập GitHub OAuth, quản lý phiên đăng nhập và đăng xuất. Các chức năng chấm điểm năng lực, AI Mentor, roadmap và CV/JD matching vẫn là định hướng phát triển tiếp theo.

> Cấu hình Docker Compose dưới đây dùng cho **môi trường phát triển**, không phải cấu hình triển khai production.

> Cấu hình Docker Compose dưới đây dùng cho **môi trường phát triển**, không phải cấu hình triển khai production.

## 1. Công nghệ và kiến trúc

| Thành phần | Công nghệ | Vai trò |
| --- | --- | --- |
| Frontend | React 19, TypeScript, Vite | Giao diện web và trang kiểm tra hệ thống |
| Backend | Python 3.12, FastAPI, SQLAlchemy | API, kiểm tra sức khỏe các dịch vụ |
| Database | PostgreSQL 17 | Lưu trữ dữ liệu |
| Queue | Redis 7 | Hàng đợi tác vụ nền |
| Worker | RQ (Redis Queue) | Nhận và xử lý tác vụ, có job `ping` để kiểm thử |
| Migration | Alembic | Quản lý phiên bản cấu trúc database |
| Development environment | Docker Compose | Khởi động các dịch vụ thống nhất giữa các máy |

```text
Trình duyệt ─── http://localhost:5173 ───▶ Frontend (Vite)
                                                 │
                                                 │ /api/* (proxy)
                                                 ▼
                                           Backend (FastAPI)
                                              │       │
                                      PostgreSQL     Redis ◀──── Worker (RQ)
```

Trong Docker Compose, các dịch vụ gọi nhau bằng **tên service** (`backend`, `postgres`, `redis`), thay vì `localhost`.

## 2. Yêu cầu cài đặt

Cách chạy chuẩn cho thành viên nhóm là **Docker Compose**. Cần chuẩn bị:

- **Git** để clone repository.
- **Docker Desktop** trên Windows/macOS (hoặc Docker Engine + Docker Compose plugin trên Linux).
- Docker Engine đang chạy. Trên Windows, Docker Desktop cần được cấu hình với Linux containers/WSL2 phù hợp.
- Có thể sử dụng các cổng `5173`, `8000`, `5432`, `6379` trên máy, hoặc điều chỉnh các cổng host trong `.env`.

**Không cần cài Python, Node.js, PostgreSQL hay Redis trực tiếp trên máy** nếu chỉ chạy bằng Docker Compose. Những công cụ đó chỉ cần khi phát triển hoặc chạy một service bên ngoài Docker.

Kiểm tra Docker trong Terminal:

```powershell
docker --version
docker compose version
docker info
```

## 3. Cài đặt và chạy lần đầu (khuyến nghị)

> **Tất cả lệnh Docker Compose ở phần này phải chạy tại thư mục gốc repository**, nơi chứa `docker-compose.yml`.

### Bước 1 – Clone repository

Qua SSH (nếu đã cấu hình SSH key với GitHub):

```powershell
git clone git@github.com:Tom-Hallo/IT_AI_Profile.git
cd IT_AI_Profile
```

Hoặc qua HTTPS:

```powershell
git clone https://github.com/Tom-Hallo/IT_AI_Profile.git
cd IT_AI_Profile
```

### Bước 2 – Tạo file cấu hình `.env`

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

**Linux/macOS:**

```bash
cp .env.example .env
```

Mở `.env` để kiểm tra các giá trị phù hợp với máy. File `.env.example` chỉ chứa giá trị mẫu; không sử dụng mật khẩu mẫu trong môi trường thực tế.

**Không commit `.env`, API key, GitHub token hoặc thông tin bí mật lên repository.**

### Bước 3 – Chạy script setup

**Windows PowerShell:**

```powershell
.\scripts\setup.ps1
```

Nếu chính sách thực thi PowerShell chặn script, chỉ với script đã kiểm tra và tin cậy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

**Linux/macOS:**

```bash
bash scripts/setup.sh
```

Script sẽ: kiểm tra Docker, tạo `.env` nếu chưa có, xác thực cấu hình Compose, build và khởi động các service, chạy `alembic upgrade head`, rồi in trạng thái container. Nếu thành công sẽ hiển thị:

```text
SETUP COMPLETED SUCCESSFULLY
```

**Lưu ý:** Nếu `.env` đã tồn tại, script **không ghi đè**. Ở giai đoạn PBI-001, Alembic mới có migration baseline; chưa tạo các bảng nghiệp vụ cho tính năng tương lai.

### Bước 4 – Mở ứng dụng

| Địa chỉ | Mục đích |
| --- | --- |
| <http://localhost:5173> | Giao diện Frontend và trang kiểm tra hệ thống |
| <http://localhost:8000/api/v1/health> | Healthcheck Backend, PostgreSQL và Redis |
| <http://localhost:8000/docs> | Swagger UI khi `APP_ENV=development` |

Nếu đổi `FRONTEND_PORT` hoặc `BACKEND_PORT` trong `.env`, hãy thay cổng tương ứng trong các địa chỉ trên.

## 4. Sử dụng Docker Compose hằng ngày

```powershell
# Xem 5 service và trạng thái container
docker compose ps

# Khởi động lại các container đã tạo
docker compose up -d

# Build lại khi Dockerfile hoặc dependency thay đổi
docker compose up -d --build

# Xem log của một service
docker compose logs --tail 100 backend
docker compose logs --tail 100 worker

# Theo dõi log trực tiếp
docker compose logs -f backend

# Dừng và gỡ các container thuộc Compose, giữ nguyên volume dữ liệu
docker compose down
```

Các service là `frontend`, `backend`, `postgres`, `redis`, `worker`. Trạng thái mong đợi: Frontend/Backend/PostgreSQL/Redis `healthy`, Worker `Up` (Worker chưa được khai báo healthcheck riêng).

**Cảnh báo dữ liệu:** Không dùng `docker compose down -v` tùy tiện. Tùy chọn `-v` xóa các volume của dự án, bao gồm volume dữ liệu PostgreSQL.

## 5. Kiểm tra hệ thống và Worker

### Kiểm tra Backend

**PowerShell:**

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
```

**Hoặc dùng cURL:**

```powershell
curl.exe -i http://localhost:8000/api/v1/health
```

Khi hoạt động tốt, API trả HTTP `200` và dữ liệu tương tự:

```json
{
  "status": "ok",
  "service": "backend",
  "version": "0.1.0",
  "checks": {
    "database": "ok",
    "redis": "ok"
  }
}
```

Nếu PostgreSQL hoặc Redis không khả dụng, API trả HTTP `503`, `status: "degraded"`, và thành phần bị lỗi có giá trị `"fail"`.

### Kiểm tra Worker xử lý job

Chạy từ thư mục gốc, khi các service đang hoạt động:

```powershell
docker compose exec backend python -m app.workers.enqueue ping --message "PBI001-test" --wait 15
```

Job đạt khi có `status: finished` và kết quả chứa `"pong": true`. Nếu job đứng ở `queued`, kiểm tra `docker compose ps` và log Worker:

```powershell
docker compose logs --tail 100 worker
```

## 6. Chạy kiểm thử

### Backend

```powershell
# Unit tests và các test không yêu cầu dịch vụ thực
docker compose exec backend pytest

# Chạy riêng test trong module Worker
docker compose exec backend pytest tests/workers

# Chạy integration test có sử dụng dịch vụ thật
docker compose exec -e RUN_INTEGRATION=1 backend pytest tests
```

Integration tests cần các service liên quan hoạt động ổn định. Kiểm tra báo cáo để phân biệt `passed`, `failed`, `skipped`; không coi `skipped` là đã kiểm thử thành công.

### Frontend

```powershell
docker compose exec frontend npm run typecheck
docker compose exec frontend npm run lint
docker compose exec frontend npm run build
```

### GitHub Actions (CI)

Workflow tại `.github/workflows/ci.yml` chạy kiểm tra Backend và Frontend khi có `push` lên `master` hoặc Pull Request nhắm tới `master`. Kiểm tra kết quả trong tab **Actions / Checks** của GitHub trước khi merge.

CI hiện tại chủ yếu chạy kiểm thử tự động không yêu cầu database/Redis thật; các kịch bản tích hợp và mất kết nối vẫn cần kiểm thử riêng.

## 7. Kiểm thử sự cố (chỉ trên máy phát triển)

> Các bước này chủ động làm dịch vụ ngừng hoạt động. Không thực hiện trên môi trường dùng chung hoặc production.

**PostgreSQL mất kết nối:**

```powershell
docker compose stop postgres
curl.exe -i http://localhost:8000/api/v1/health
# Mong đợi: HTTP 503, checks.database = fail

docker compose start postgres
```

**Redis mất kết nối:**

```powershell
docker compose stop redis
curl.exe -i http://localhost:8000/api/v1/health
# Mong đợi: HTTP 503, checks.redis = fail

docker compose start redis
```

Sau mỗi thử nghiệm, đợi dịch vụ sẵn sàng rồi kiểm tra API trở lại `status: ok`. Tránh chạy đồng thời hai thử nghiệm nếu muốn xác định chính xác thành phần gây lỗi.

Kiểm tra Git không theo dõi file `.env`:

```powershell
git ls-files | Select-String '(^|/)\.env$'
```

Kết quả mong đợi: **không có dòng nào**.

## 8. Biến môi trường và lưu ý bảo mật

Nguồn chuẩn cho Docker Compose là file **`.env` ở thư mục gốc**, tạo từ `.env.example`.

| Biến | Mục đích |
| --- | --- |
| `APP_ENV` | Môi trường ứng dụng (`development`, `test`, `production`) |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Cấu hình PostgreSQL |
| `POSTGRES_PORT`, `REDIS_PORT` | Cổng PostgreSQL/Redis trên máy host |
| `BACKEND_PORT`, `FRONTEND_PORT` | Cổng Backend/Frontend trên máy host |
| `VITE_API_BASE_URL` | Đường dẫn API phía trình duyệt (thường là `/api/v1`) |
| `CORS_ORIGINS` | Danh sách origin được phép theo cấu hình Backend |
| `WORKER_QUEUES` | Danh sách hàng đợi Worker |
| `FRONTEND_WATCH_POLLING` | Bật polling nếu hot-reload không hoạt động trên Windows |

Trong Docker Compose, `DATABASE_URL` và `REDIS_URL` được tạo từ cấu hình Compose. Nếu **chạy trực tiếp trên máy**, sử dụng `backend/.env.example` và `frontend/.env.example` riêng; xem tài liệu của từng thành phần.

Không đặt secret trong biến bắt đầu bằng `VITE_`, vì các biến này có thể được đưa vào mã chạy trên trình duyệt. Redis/PostgreSQL trong Compose được publish trên `127.0.0.1` để hạn chế truy cập từ mạng ngoài.

## 8.1. GitHub OAuth – PBI-005

### 8.1.1. Tạo GitHub OAuth App

Truy cập:

https://github.com/settings/developers

Chọn **OAuth Apps → New OAuth App** và cấu hình:

| Trường | Giá trị |
| --- | --- |
| Application name | IT AI Profile |
| Homepage URL | http://localhost:5173 |
| Authorization callback URL | http://localhost:8001/api/v1/auth/github/callback |

Sau khi tạo OAuth App, lấy `Client ID` và tạo `Client Secret`.

### 8.1.2. Cấu hình Backend

Thêm các biến sau vào file `backend/.env`:

```env
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
GITHUB_REDIRECT_URI=http://localhost:8001/api/v1/auth/github/callback

## 9. Cấu trúc thư mục chính

```text
IT_AI_Profile/
├── .env.example                 # Mẫu cấu hình chung cho Compose
├── docker-compose.yml           # 5 service phát triển
├── scripts/
│   ├── setup.ps1                # Thiết lập trên Windows
│   └── setup.sh                 # Thiết lập trên Linux/macOS
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── src/
│   └── README.md                # Tài liệu frontend chi tiết
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── app/
│   │   ├── api/health.py
│   │   ├── db/
│   │   └── workers/
│   │       └── README.md        # Tài liệu Worker chi tiết
│   ├── migrations/
│   │   └── README.md            # Tài liệu Alembic chi tiết
│   └── tests/
└── .github/
    └── workflows/ci.yml
```

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân / cách xử lý |
| --- | --- |
| `docker is not recognized` | Docker CLI chưa được cài hoặc Terminal chưa nhận PATH. Mở Docker Desktop, mở lại VS Code/PowerShell, kiểm tra `docker --version`. |
| `Cannot connect to the Docker daemon` | Docker Engine chưa chạy; mở Docker Desktop và kiểm tra `docker info`. |
| `port is already allocated` | Cổng host đang bị chương trình/container khác chiếm. Kiểm tra `docker ps -a`, dừng tiến trình cũ **nếu không còn dùng**, hoặc đổi cổng host trong `.env`. |
| `docker compose ps` không có service | Chạy trong đúng thư mục chứa `docker-compose.yml`, rồi dùng `docker compose up -d`. |
| Backend trả `503` | PostgreSQL/Redis chưa khỏe hoặc sai cấu hình; xem `docker compose ps` và `docker compose logs backend`. |
| Worker nhận job nhưng không xử lý | Kiểm tra `docker compose logs worker`, `WORKER_QUEUES`, trạng thái Redis. |
| Frontend không gọi được Backend | Kiểm tra `VITE_API_BASE_URL=/api/v1`, proxy đến `http://backend:8000`, xem log Frontend/Backend; khởi động lại khi thay đổi env. |
| Sửa mã nguồn không tự cập nhật trên Windows | Bật `FRONTEND_WATCH_POLLING=true` rồi khởi động lại Frontend. |
| PostgreSQL sai mật khẩu sau khi đổi `.env` | Mật khẩu trong volume PostgreSQL đã khởi tạo không tự đổi theo `.env`; cần xử lý/migrate credentials, **không xóa volume khi còn dữ liệu quan trọng**. |
| Script PowerShell không chạy | Kiểm tra Execution Policy và nội dung script; chỉ dùng lệnh bypass một lần với script đáng tin cậy. |

## 11. Quy trình làm việc nhóm

1. Đồng bộ `master`, tạo branch riêng theo nhiệm vụ (`feature/...`, `fix/...`).
2. Thay đổi code, chạy các kiểm thử phù hợp, kiểm tra `git status` và `git diff`.
3. Commit/push **branch riêng**; không commit file `.env` hoặc secret.
4. Tạo Pull Request vào `master`, yêu cầu một thành viên khác review.
5. Chỉ merge khi review và các kiểm tra bắt buộc đạt yêu cầu; cập nhật Trello tương ứng.

## 12. Tài liệu chi tiết

- [Frontend](frontend/README.md) – Vite, React, cấu hình API proxy, chạy riêng và kiểm thử giao diện.
- [RQ Worker](backend/app/workers/README.md) – enqueue, hàng đợi, xử lý job và integration test.
- [Database migrations](backend/migrations/README.md) – Alembic, migration baseline và quy trình tạo revision mới.

---

**Phạm vi tài liệu:** Hướng dẫn môi trường phát triển PBI-001. Khi các tính năng AI/GitHub/CV/JD được bổ sung, tài liệu sẽ cần được cập nhật tương ứng.
