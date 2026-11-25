# IT Talent AI Profile

**IT Talent AI Profile** – Hồ sơ năng lực CNTT thông minh dành cho developer. Ứng dụng kết nối GitHub, phân tích bằng chứng đóng góp, đánh giá năng lực theo kỹ năng và vai trò, hỗ trợ định hướng nghề nghiệp, xây dựng lộ trình học tập và chuẩn bị CV theo yêu cầu tuyển dụng.

> Tài liệu này hướng dẫn chạy và bàn giao bản ứng dụng trên nhánh `master` trong môi trường phát triển/localhost. Docker Compose hiện tại sử dụng hot reload và không phải cấu hình triển khai production. Các tính năng phụ thuộc vào quyền GitHub, dữ liệu minh chứng, cấu hình AI và trạng thái dịch vụ; có API không đồng nghĩa mọi kịch bản đã được nghiệm thu.

## 1. Chức năng hiện có

| Chức năng | Phạm vi hiện có trong mã nguồn |
| --- | --- |
| Tài khoản và GitHub | Đăng nhập OAuth, quản lý phiên, đăng xuất, ngắt kết nối, đồng bộ và lựa chọn repository. |
| Phân tích repository | Tạo tác vụ phân tích, theo dõi trạng thái, kiểm tra đóng góp và đọc báo cáo/minh chứng. |
| Dashboard năng lực | Điểm kỹ năng, điểm vai trò, radar, confidence, coverage và bằng chứng theo phạm vi dữ liệu. |
| AI Mentor | Hỏi đáp theo nguồn được chọn, hỗ trợ tư vấn nghề nghiệp; đề xuất hành động và xử lý quyết định người dùng. |
| Career Roadmap | Tạo, xem lộ trình theo mục tiêu; theo dõi cột mốc, nộp minh chứng, lịch sử và đánh giá lại. |
| Job Matches | Phân tích mô tả công việc (JD), đối chiếu yêu cầu với năng lực và tìm kiếm việc làm qua API hiện có. |
| CV Intelligence | Tiếp nhận, xem trước và quản lý CV; phân tích/phản hồi ATS và hỗ trợ đối chiếu JD. |
| CV Studio | Tạo CV dựa trên nguồn minh chứng, quản lý phiên bản và xuất tài liệu. |
| Analysis & Privacy | Quản lý consent, phạm vi truy cập dữ liệu và theo dõi hoạt động liên quan đến phân tích/AI. |
| Hồ sơ và lịch sử | API chia sẻ hồ sơ, thu hồi liên kết, snapshot lịch sử và so sánh kết quả. |
| Đánh giá bổ sung | API kỹ năng tự khai báo, đánh giá năng lực, mẫu CV và telemetry. |

Các nhóm API được đăng ký trong [backend/app/api/router.py](backend/app/api/router.py). Danh sách endpoint đầy đủ xem tại Swagger khi backend chạy ở chế độ development. Một số chức năng bổ sung có thể được cung cấp ở tầng API; không mặc định rằng mỗi router có một màn hình riêng.

**Giới hạn cần hiểu:** điểm năng lực phản ánh dữ liệu và rubric của hệ thống, không thay thế đánh giá chuyên môn của nhà tuyển dụng. Thiếu minh chứng có thể dẫn tới trạng thái chưa đủ dữ liệu; không đồng nhất với điểm 0. AI có thể đưa ra nội dung chưa chính xác, nên người dùng cần kiểm tra lại đề xuất và thông tin CV. Phản hồi ATS và matching không đảm bảo kết quả tuyển dụng.

## 2. Kiến trúc và công nghệ

| Thành phần | Công nghệ / vai trò |
| --- | --- |
| Frontend | HTML, CSS, JavaScript (Pixel Studio); repository còn có React 19, TypeScript và React Router. Vite 8 chạy và build giao diện. |
| Backend | Python 3.12, FastAPI, Uvicorn, SQLAlchemy, psycopg, Pydantic Settings. |
| Database | PostgreSQL 17; lưu dữ liệu nghiệp vụ và báo cáo. |
| Migration | Alembic; quản lý phiên bản schema. |
| Queue / Worker | Redis 7 và RQ; tiếp nhận, xử lý tác vụ nền. |
| Maintenance | Tiến trình bảo trì của backend. |
| CV scanner | ClamAV; phục vụ kiểm tra tệp CV tải lên. |
| AI | Adapter phía backend cho Ollama, Gemini và OpenAI; cấu hình qua biến môi trường. |
| Môi trường chạy | Docker Compose; Dockerfile backend và frontend cho phát triển. |
| Kiểm thử | pytest, Ruff, ESLint, TypeScript, Node test runner, GitHub Actions. |

```text
Browser ── http://localhost:5173 ── Frontend (Vite / Pixel Studio)
                                      │ /api/* (proxy)
                                      ▼
                              Backend (FastAPI :8000)
                                │      │       │
                           PostgreSQL Redis   ClamAV
                                │      │
                                │      ├── Worker (RQ)
                                │      └── Maintenance
                                └── Migration (Alembic)

Backend / Worker ── AI provider (theo cấu hình)
Backend ── GitHub OAuth / GitHub API
```

Entrypoint frontend đang dùng là [frontend/index.html](frontend/index.html), nạp `src/pixel-studio/app.js` với `data-studio-mode="live"`. React/TypeScript vẫn tồn tại trong repository nhưng không nên mô tả toàn bộ giao diện hiện tại là React. Vite proxy `/api` đến `http://backend:8000` trong Docker, không loại bỏ prefix. Các container gọi nhau qua tên service, không dùng `localhost` để gọi container khác.

## 3. Yêu cầu cài đặt

- Git và quyền truy cập repository.
- Docker Desktop (Windows/macOS) hoặc Docker Engine + Compose plugin (Linux), đang chạy; Windows dùng Linux containers/WSL2 phù hợp.
- Internet khi tải image/dependency, thực hiện GitHub OAuth/API hoặc gọi AI cloud.
- GitHub OAuth App để đăng nhập thực tế.
- AI provider đã cấu hình nếu sử dụng tính năng cần AI. Ollama mặc định chạy bên ngoài Compose.
- Các cổng host mặc định 5173, 8000, 5432, 6379 còn trống hoặc được thay đổi trong `.env`.

Không cần cài riêng Python, Node.js, PostgreSQL hay Redis để chạy Compose. Nếu chọn Ollama local, cần một Ollama server và model tương ứng.

```sh
docker --version
docker compose version
docker info
```

## 4. Cài đặt lần đầu

Chạy các lệnh tại thư mục gốc repository, nơi có `docker-compose.yml`.

### Bước 1 – Clone

```sh
git clone https://github.com/Tom-Hallo/IT_AI_Profile.git
cd IT_AI_Profile
git switch master
```

### Bước 2 – Tạo `.env`

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

Chỉ sao chép nếu chưa có `.env`. Không ghi đè cấu hình hoặc khóa của môi trường đang sử dụng. Thay mật khẩu mẫu và thiết lập các biến cần thiết theo phần 5–6.

**Bắt buộc:** `.env.example` đang để trống `GITHUB_TOKEN_ENCRYPTION_KEY`, trong khi Compose yêu cầu giá trị không rỗng. Tạo khóa mới cho môi trường cài lần đầu bằng lệnh sau (không cần Python trên host):

```sh
docker run --rm python:3.12-slim python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Sao chép kết quả vào `GITHUB_TOKEN_ENCRYPTION_KEY` trong `.env`. Giữ khóa bí mật, ổn định giữa các lần khởi động; thay khóa tùy tiện có thể làm token/dữ liệu đã mã hóa không đọc được. Không đưa khóa lên GitHub hoặc log chia sẻ.

### Bước 3 – Khởi động

Sau khi hoàn thành cấu hình, chạy:

```sh
docker compose config --quiet
docker compose up -d --build --wait
docker compose ps -a
```

Service `migrate` chạy `alembic upgrade head` trước khi backend/worker khởi động. Nếu migration thành công, container này kết thúc với exit code 0; không cần giữ nó chạy liên tục.

Có thể dùng script setup thay cho các lệnh trên sau khi chuẩn bị `.env`:

Windows PowerShell:

```powershell
.\scripts\setup.ps1
```

Nếu bị Execution Policy chặn và đã kiểm tra script:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Linux/macOS:

```bash
bash scripts/setup.sh
```

Script kiểm tra Docker, validate Compose, build, start và chạy lại `alembic upgrade head`; không ghi đè `.env` đã tồn tại. Script không tự tạo encryption key. URL script in ra sử dụng cổng mặc định.

### Bước 4 – Truy cập

| Địa chỉ mặc định | Mục đích |
| --- | --- |
| <http://localhost:5173> | Giao diện người dùng |
| <http://localhost:8000/api/v1/health> | Kiểm tra backend, PostgreSQL, Redis |
| <http://localhost:5173/api/v1/health> | Kiểm tra kết nối qua Vite proxy |
| <http://localhost:8000/api/v1/docs> | Swagger UI |
| <http://localhost:8000/api/v1/openapi.json> | OpenAPI schema |

Swagger và OpenAPI chỉ bật khi `APP_ENV=development`; ReDoc bị tắt. API prefix là `/api/v1`, không phải `/docs` ở root. Nếu đổi cổng host, sử dụng địa chỉ tương ứng. Một số endpoint cần phiên đăng nhập và kiểm tra CSRF; mở Swagger không thay thế việc đăng nhập qua giao diện.

## 5. GitHub OAuth và cấu hình môi trường

### GitHub OAuth App

Mở <https://github.com/settings/developers>, chọn **OAuth Apps → New OAuth App**.

| Trường | Giá trị mặc định |
| --- | --- |
| Application name | IT Talent AI Profile |
| Homepage URL | `http://localhost:5173` |
| Authorization callback URL | `http://localhost:8000/api/v1/auth/github/callback` |

Lấy Client ID và tạo Client Secret. Với Docker Compose, chỉnh **`.env` ở thư mục gốc** (không phải chỉ `backend/.env`):

```dotenv
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret
GITHUB_REDIRECT_URI=http://localhost:8000/api/v1/auth/github/callback
FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=http://localhost:5173
```

Thay placeholder bằng thông tin thực; giữ encryption key đã tạo ở bước 2. OAuth chỉ được bật khi có đủ Client ID và Secret. Backend nhận callback, xử lý OAuth/session và chuyển hướng về `FRONTEND_URL`. Nếu đổi port backend, cập nhật cả callback trong GitHub và `GITHUB_REDIRECT_URI`; nếu đổi port frontend, cập nhật `FRONTEND_URL`, `CORS_ORIGINS` và Homepage URL. Dùng thống nhất hostname `localhost` trong trình duyệt và cấu hình OAuth.

### Biến môi trường chính

| Biến | Mặc định/mục đích |
| --- | --- |
| `APP_ENV`, `LOG_LEVEL` | `development`, `INFO` |
| `POSTGRES_DB` | `ai_talent_profile` trong `.env.example`; giữ tên DB đã cấu hình với volume hiện hữu |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Tài khoản/mật khẩu PostgreSQL; thay mật khẩu mẫu khi cài mới |
| `POSTGRES_PORT`, `REDIS_PORT` | `5432`, `6379` (cổng host) |
| `BACKEND_PORT`, `FRONTEND_PORT` | `8000`, `5173` (cổng host) |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | OAuth App; cần cho đăng nhập GitHub |
| `GITHUB_REDIRECT_URI` | `http://localhost:8000/api/v1/auth/github/callback` |
| `GITHUB_TOKEN_ENCRYPTION_KEY` | Khóa base64 URL-safe biểu diễn 32 byte, bắt buộc trong Compose |
| `FRONTEND_URL`, `CORS_ORIGINS` | `http://localhost:5173`; CORS hỗ trợ danh sách phân tách bằng dấu phẩy |
| `VITE_API_BASE_URL` | `/api/v1` |
| `FRONTEND_WATCH_POLLING` | `true` trong Compose; hỗ trợ hot reload |
| `WORKER_QUEUES` | `default` |

Compose tự tạo `DATABASE_URL` và `REDIS_URL` dùng `postgres:5432` và `redis:6379`. Đổi cổng host không đổi cổng nội bộ. Nếu chạy service ngoài Docker, xem `.env.example` riêng của thành phần tương ứng (nếu có) và cấu hình địa chỉ phù hợp.

## 6. Cấu hình AI

AI được gọi từ backend/worker; không gửi API key của nhà cung cấp xuống trình duyệt. Compose hỗ trợ `ollama`, `gemini`, `openai`. Các biến sau hiện có trong Compose dù chưa được liệt kê đầy đủ trong `.env.example` gốc.

### Ollama local (mặc định Compose)

Cài Ollama theo hướng dẫn tại <https://ollama.com/download>, khởi động server trên máy host và tải model:

```sh
ollama pull qwen2.5:3b
```

Thêm hoặc điều chỉnh `.env`:

```dotenv
AI_PROVIDER=ollama
AI_MODEL=qwen2.5:3b
AI_BASE_URL=http://host.docker.internal:11434
AI_API_KEY=
```

Ollama không phải service trong Compose hiện tại. Docker Desktop thường hỗ trợ `host.docker.internal`; trên Linux cần kiểm tra host gateway và khả năng kết nối từ container. Đảm bảo Ollama server lắng nghe tại địa chỉ container truy cập được, không mở cổng ra Internet tùy tiện.

### Gemini hoặc OpenAI

Chọn `AI_PROVIDER=gemini` hoặc `AI_PROVIDER=openai`, đặt `AI_API_KEY` của nhà cung cấp tương ứng và `AI_MODEL` là tên model mà tài khoản được phép sử dụng. `AI_BASE_URL` dùng cho Ollama; adapter OpenAI và Gemini hiện gọi endpoint cloud cố định trong mã nguồn (`https://api.openai.com/v1/responses` và `https://generativelanguage.googleapis.com/v1beta/models`). Không cần đổi `AI_BASE_URL` khi chuyển sang hai provider này. Xem implementation trong [backend/app/ai/providers/](backend/app/ai/providers/). Không commit API key. Các dịch vụ cloud có thể phát sinh phí và giới hạn tốc độ.

| Biến giới hạn | Mặc định Compose |
| --- | --- |
| `AI_TIMEOUT_SECONDS` | 120 |
| `AI_MAX_INPUT_CHARS` | 50000 |
| `AI_MAX_OUTPUT_TOKENS` | 2000 |
| `AI_MAX_REQUESTS_PER_DAY` | 50 |

Sau khi đổi `.env`, tái tạo service để nhận biến mới:

```sh
docker compose up -d --force-recreate backend worker maintenance frontend
```

Khi AI lỗi, kiểm tra provider, model, key, kết nối và log. Healthcheck backend không kiểm tra AI. Chỉ sử dụng nguồn dữ liệu được cấp quyền và consent phù hợp, đặc biệt khi gửi dữ liệu private repository đến AI bên ngoài.

## 7. Docker Compose và vận hành

| Service | Vai trò / trạng thái dự kiến |
| --- | --- |
| `postgres` | PostgreSQL, healthy |
| `redis` | Redis, healthy |
| `migrate` | Alembic one-shot, Exited (0) khi hoàn thành |
| `backend` | FastAPI, healthy |
| `worker` | RQ worker, Up |
| `maintenance` | Tiến trình bảo trì, Up |
| `clamav` | Scanner CV, Up; cần thời gian sẵn sàng/cập nhật chữ ký |
| `frontend` | Vite, healthy |

`worker`, `maintenance` và `clamav` không có healthcheck riêng được khai báo trong Compose; trạng thái thực tế có thể phụ thuộc image. Backend chờ PostgreSQL, Redis và migration; frontend chờ backend healthy. Mạng `cv_scanner` kết nối backend với ClamAV. Các cổng host được bind tới `127.0.0.1`.

```sh
docker compose ps -a
docker compose up -d
docker compose up -d --build
docker compose logs --tail 100 backend worker
docker compose logs -f backend
docker compose down
```

`docker compose down` giữ named volumes theo mặc định. **Không dùng `docker compose down -v`** nếu cần giữ dữ liệu: lệnh xóa các volume, bao gồm PostgreSQL. Đổi mật khẩu trong `.env` không tự đổi mật khẩu database đã khởi tạo.

## 8. API và luồng sử dụng

Các đường dẫn dưới đây đều có prefix `/api/v1`; đây là ví dụ, không phải danh mục toàn bộ API.

| Method và endpoint | Chức năng |
| --- | --- |
| `GET /api/v1/health` | Healthcheck công khai |
| `GET /api/v1/auth/github` | Khởi tạo OAuth |
| `GET /api/v1/auth/github/callback` | Nhận callback OAuth |
| `GET /api/v1/auth/me` | Thông tin phiên hiện tại |
| `POST /api/v1/analysis/jobs` | Tạo job phân tích |
| `GET /api/v1/analysis/jobs/{job_id}` | Đọc trạng thái job |
| `GET /api/v1/repositories/{repository_id}/analysis/dashboard-radar` | Dữ liệu radar repository |
| `GET /api/v1/role-scoring/roles/{role_key}/score/scoped` | Điểm vai trò theo phạm vi |
| `POST /api/v1/mentor/chat` | Hỏi AI Mentor |
| `POST /api/v1/agent/actions/{action_id}/{decision}` | Quyết định đối với đề xuất Agent |
| `POST /api/v1/career-roadmaps` | Tạo roadmap |
| `GET /api/v1/roadmap-tracking/{roadmap_id}` | Theo dõi roadmap |
| `POST /api/v1/jobs/analyze` | Phân tích JD |
| `POST /api/v1/jobs/match` | Đối chiếu yêu cầu công việc |
| `POST /api/v1/cvs/preview` | Xem trước CV tải lên |
| `POST /api/v1/ats-reviews/preview` | Xem phản hồi ATS |
| `POST /api/v1/cv-studio/generate` | Tạo CV |
| `GET /api/v1/historical/snapshots` | Danh sách snapshot lịch sử |
| `GET /api/v1/profile/shares` | Quản lý liên kết chia sẻ |

Luồng demo đề xuất:

1. Đăng nhập GitHub, đồng ý phạm vi quyền phù hợp và đồng bộ repository.
2. Chọn repository, yêu cầu phân tích, theo dõi tiến độ đến khi có báo cáo.
3. Mở Dashboard, xem điểm, confidence, coverage và minh chứng liên quan. Khi chưa đủ dữ liệu, giữ trạng thái chưa đủ bằng chứng.
4. Hỏi AI Mentor với nguồn đã chọn; kiểm tra đề xuất và xác nhận hành động nếu cần.
5. Tạo roadmap theo mục tiêu, theo dõi cột mốc, nộp minh chứng và đánh giá lại.
6. Phân tích JD, đối chiếu kỹ năng, kiểm tra CV/ATS hoặc tạo CV Studio, xem lại nội dung trước khi xuất.

Điểm theo phạm vi public/private/combined phụ thuộc quyền và consent; combined cần tránh tính trùng bằng chứng. Không dùng kết quả từ repository chưa được cấp quyền. Mức độ đầy đủ của báo cáo phụ thuộc dữ liệu và giới hạn phân tích.

## 9. Kiểm tra hệ thống và kiểm thử

PowerShell:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-RestMethod http://localhost:5173/api/v1/health
```

Linux/macOS:

```bash
curl -i http://localhost:8000/api/v1/health
curl -i http://localhost:5173/api/v1/health
```

Phản hồi mẫu khi database và Redis hoạt động:

```json
{
  "status": "ok",
  "service": "backend",
  "version": "0.1.0",
  "checks": { "database": "ok", "redis": "ok" }
}
```

HTTP 503 và `status: degraded` báo database hoặc Redis không khả dụng. HTTP 200 không chứng minh GitHub, AI, worker hay ClamAV đã sẵn sàng.

Kiểm tra migration và worker:

```sh
docker compose exec backend alembic current
docker compose exec backend alembic heads
docker compose exec redis redis-cli ping
docker compose exec backend python -m app.workers.enqueue ping --message "handover-test" --wait 15
```

Job ping thành công khi trạng thái `finished` và kết quả có `pong: true`.

### Backend

```sh
docker compose exec backend ruff check .
docker compose exec backend ruff format --check .
docker compose exec backend pytest -m "not integration"
```

Integration test chỉ chạy trên môi trường/database kiểm thử phù hợp, không dùng dữ liệu bàn giao quan trọng. Kiểm tra fixture, quyền tạo database tạm và các dependency trước khi chạy, ví dụ:

```sh
docker compose exec -e RUN_INTEGRATION=1 backend pytest -m integration
```

### Frontend

```sh
docker compose exec frontend npm run typecheck
docker compose exec frontend npm run lint
docker compose exec frontend npm run test
docker compose exec frontend npm run build
```

`npm run test` hiện gọi các nhóm evidence, roadmap và CV Studio. CI còn có các regression test khác (dashboard radar, score presentation, analysis feedback và mentor proposal). Xem [.github/workflows/ci.yml](.github/workflows/ci.yml) để chạy đúng phạm vi CI. Workflow có backend unit tests, frontend checks, regression PostgreSQL cho Mentor/Roadmap và secret scan. Kết quả skipped không phải passed; không suy ra toàn bộ hệ thống đã nghiệm thu từ lint/build.

## 10. Cấu trúc source chính

```text
IT_AI_Profile/
├── README.md
├── .env.example
├── docker-compose.yml
├── scripts/                    # Setup Windows/Linux/macOS
├── frontend/
│   ├── index.html              # Entrypoint Vite hiện tại
│   ├── vite.config.ts           # Proxy và dev server
│   ├── package.json
│   ├── Dockerfile
│   ├── public/pixel-studio/     # CSS và tài nguyên giao diện
│   ├── src/pixel-studio/        # UI JavaScript và kết nối API
│   ├── src/app/                # React/TypeScript application code
│   └── tests/                  # Frontend regression tests
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── app/
│   │   ├── main.py             # FastAPI entrypoint
│   │   ├── api/router.py       # Tổng hợp router
│   │   ├── core/config.py      # Biến môi trường
│   │   ├── modules/            # Các module nghiệp vụ
│   │   ├── ai/providers/       # AI provider adapters
│   │   ├── db/                 # Database models/session
│   │   └── workers/            # RQ và maintenance
│   ├── migrations/             # Alembic migrations
│   └── tests/                  # Backend tests
└── .github/workflows/ci.yml
```

## 11. Xử lý lỗi thường gặp

| Hiện tượng | Cách kiểm tra/xử lý |
| --- | --- |
| Compose báo encryption key required | Tạo khóa hợp lệ và điền vào `.env` gốc trước khi chạy Compose. |
| Docker daemon không kết nối | Mở Docker Desktop, kiểm tra `docker info`. |
| Port đã được sử dụng | Kiểm tra tiến trình/container đang chiếm cổng; đổi host port trong `.env` nếu cần. |
| Migration thất bại / backend không start | `docker compose logs migrate postgres backend`; kiểm tra DB credentials, schema và revision. |
| Backend trả 503 | Kiểm tra PostgreSQL/Redis và log backend. |
| Swagger 404 | Dùng `/api/v1/docs` và `APP_ENV=development`. |
| OAuth callback lỗi | So khớp URL trên GitHub OAuth App và `GITHUB_REDIRECT_URI`; kiểm tra port và Client ID/Secret. |
| Đăng nhập xong không về giao diện | Kiểm tra `FRONTEND_URL`, `CORS_ORIGINS`, port, hostname. |
| Frontend không gọi được API | Kiểm tra health qua port 5173, proxy `http://backend:8000` và log. |
| Job đứng queued | Kiểm tra Redis, `WORKER_QUEUES` và log worker. |
| AI không phản hồi | Kiểm tra provider, key, model, timeout và kết nối từ container. |
| CV không tải lên được | Kiểm tra định dạng, giới hạn tệp, ClamAV và log; không tắt scanner để bỏ qua lỗi. |
| Thay `.env` nhưng cấu hình chưa đổi | Dùng `docker compose up -d` để áp dụng thay đổi hoặc `--force-recreate` khi cần; restart đơn thuần không nạp env mới. |
| PostgreSQL sai mật khẩu sau khi đổi `.env` | Đồng bộ credentials trong database đã tồn tại; không xóa volume nếu cần giữ dữ liệu. |

## 12. Bảo mật và bàn giao

- Không commit `.env`, secret, OAuth token, API key hoặc dữ liệu CV/private repository của người dùng.
- Không đặt secret vào biến `VITE_`; chúng có thể xuất hiện ở phía client.
- Kiểm tra quyền truy cập và consent trước khi phân tích repository private hoặc gửi dữ liệu sang AI provider.
- Sao lưu database và giữ khóa mã hóa an toàn trước khi thay đổi cấu hình/migration trên môi trường có dữ liệu.
- Bản Compose hiện tại dành cho localhost/development; triển khai production cần cấu hình riêng, HTTPS, secret management, bảo vệ dịch vụ và quy trình backup/monitoring phù hợp.
- Trước bàn giao, kiểm tra cài mới, đăng nhập GitHub, phân tích, Dashboard, AI Mentor, Roadmap, JD/CV, scanner, xuất CV và các trường hợp thiếu dữ liệu/lỗi dịch vụ bằng tài khoản kiểm thử. Ghi lại kết quả thực tế; không mặc định mọi chức năng đã pass.

Quy trình đóng góp: tạo branch riêng từ `master`, kiểm thử, commit/push, mở Pull Request, review và kiểm tra CI trước khi merge.

## 13. Tài liệu và mã nguồn tham chiếu

- [Docker Compose](docker-compose.yml), [mẫu môi trường](.env.example).
- [API router](backend/app/api/router.py), [FastAPI entrypoint](backend/app/main.py), [backend settings](backend/app/core/config.py).
- [Frontend entrypoint](frontend/index.html), [Vite config](frontend/vite.config.ts), [frontend scripts](frontend/package.json).
- [AI providers](backend/app/ai/providers/), [migrations](backend/migrations/), [backend tests](backend/tests/), [frontend tests](frontend/tests/).
- [CI workflow](.github/workflows/ci.yml).

Đọc thêm [Frontend README](frontend/README.md), [Worker README](backend/app/workers/README.md) và [Migration README](backend/migrations/README.md) nếu cần chi tiết; ưu tiên cấu hình và mã nguồn đang chạy khi tài liệu phụ còn mô tả PBI cũ.
