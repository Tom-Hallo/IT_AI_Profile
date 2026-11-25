# IT Talent AI Profile

Nền tảng hồ sơ năng lực CNTT thông minh dành cho developer, kết nối GitHub, phân tích mã nguồn và đóng góp, đánh giá kỹ năng theo rubric, hỗ trợ định hướng nghề nghiệp và chuẩn bị CV.

## 1. Trạng thái chức năng

| Nhóm chức năng | Module/API đã triển khai |
|---|---|
| GitHub OAuth và đồng bộ | `auth`, `github`, lựa chọn repository, consent |
| Repository Analysis | Job nền, phân tích ngôn ngữ/framework, xác minh đóng góp, lưu evidence |
| Skill/Role Scoring và Dashboard | Rubric, điểm kỹ năng, điểm theo vai trò, báo cáo, radar, scope công khai/riêng tư/kết hợp |
| AI Mentor | Chat, nguồn thông tin, quyết định đối với đề xuất agent |
| Career Roadmap | Tạo lộ trình, tracking, nộp evidence, đánh giá lại |
| Job Matching | Phân tích JD, đối chiếu yêu cầu công việc, tìm kiếm công việc |
| CV Intelligence / Studio | Quản lý CV, tạo CV, phiên bản, xuất tài liệu, ATS review |
| Profile Sharing và Privacy | Chia sẻ hồ sơ, consent, kiểm soát truy cập, audit |

Đây là trạng thái module/API trong source code, không phải chứng nhận tất cả luồng đã chạy thành công. GitHub OAuth, dữ liệu evidence, quyền truy cập, AI provider và các dịch vụ nền phải được cấu hình và kiểm thử. Thiếu bằng chứng được biểu diễn là `Insufficient` / `score=null`, không phải điểm 0.

## 2. Kiến trúc

Frontend React 19, TypeScript, JavaScript và Vite; Backend Python 3.12, FastAPI, SQLAlchemy; PostgreSQL 17, Redis 7, RQ và Alembic; ClamAV quét CV. Frontend gọi `/api/v1` qua proxy Vite đến `http://backend:8000`. Các container gọi nhau qua service name, không dùng localhost để gọi container khác.

Compose development có 8 service: `frontend`, `backend`, `postgres`, `redis`, `worker`, `maintenance`, `clamav`, `migrate`. `migrate` là one-shot, thành công khi Exited (0). Các service còn lại phải running; service có healthcheck phải healthy. Worker, maintenance và ClamAV cần kiểm tra chức năng riêng.

## 3. Chạy development

Cần Git, Docker Desktop/Engine và Docker Compose plugin. Trên Windows sử dụng Linux containers/WSL2. Không cần cài Python/Node/PostgreSQL/Redis ở host nếu dùng Compose.

```powershell
git clone https://github.com/Tom-Hallo/IT_AI_Profile.git
cd IT_AI_Profile
# Chỉ tạo khi chưa có .env
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Cấu hình root `.env` trước khi chạy. Đặt mật khẩu DB, OAuth credentials và khóa mã hóa Fernet (base64 URL-safe của 32 bytes). Nếu đã có database/token, giữ nguyên DB name và khóa đang dùng; không ghi đè `.env`. Có thể tạo khóa cho cài đặt mới bằng Python `from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())` trong môi trường đã cài cryptography. Không đưa khóa lên Git hay log chia sẻ.

```powershell
docker info
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
```

Có thể dùng `scripts/setup.ps1` hoặc `scripts/setup.sh` theo hệ điều hành sau khi kiểm tra nội dung. Dev Compose dùng Uvicorn `--reload`, Vite dev server và bind mounts. Không dùng nó như production.

| URL mặc định | Mục đích |
|---|---|
| http://localhost:5173 | Frontend |
| http://localhost:8000/api/v1/health | Backend health |
| http://localhost:5173/api/v1/health | Health qua proxy |
| http://localhost:8000/api/v1/docs | Swagger (development only) |
| http://localhost:8000/api/v1/openapi.json | OpenAPI (development only) |

Nếu thay host port, cập nhật URL truy cập, CORS, frontend URL và OAuth callback tương ứng. Compose mặc định publish DB 5432 và Redis 6379 chỉ trên loopback; thay port host không thay container port. Tên DB theo `.env` đang sử dụng; `.env.example` hiện dùng `ai_talent_profile`, không đổi tên database đã có dữ liệu chỉ để khớp tài liệu.

## 4. GitHub OAuth / AI

Tạo OAuth App tại https://github.com/settings/developers. Homepage mặc định `http://localhost:5173`; callback mặc định `http://localhost:8000/api/v1/auth/github/callback`. Root `.env` (không phải backend/.env khi dùng Compose):

```dotenv
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_REDIRECT_URI=http://localhost:8000/api/v1/auth/github/callback
GITHUB_TOKEN_ENCRYPTION_KEY=
FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=http://localhost:5173
VITE_API_BASE_URL=/api/v1
AI_PROVIDER=ollama
AI_MODEL=qwen2.5:3b
AI_BASE_URL=http://host.docker.internal:11434
AI_API_KEY=
```

Giá trị trống là placeholder. Với Ollama, chạy dịch vụ trên host và tải model đúng cấu hình; kiểm tra kết nối từ Backend và Worker. Với OpenAI/Gemini chọn model và API key phù hợp, kiểm tra inference thực. Không đưa secret vào biến VITE_. Các giới hạn AI có thể cấu hình qua `AI_TIMEOUT_SECONDS`, `AI_MAX_INPUT_CHARS`, `AI_MAX_OUTPUT_TOKENS`, `AI_MAX_REQUESTS_PER_DAY`.

`GET /api/v1/auth/github/status` trả 204 nếu cấu hình OAuth/key sẵn sàng; cần đăng nhập thật để kiểm chứng callback và session. `backend/.env` chỉ là cấu hình chạy Backend ngoài Compose.

## 5. Kiểm tra và vận hành

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-RestMethod http://localhost:5173/api/v1/health
docker compose exec -T backend alembic current
docker compose exec -T backend alembic heads
docker compose logs --tail 100 backend worker maintenance
# Temporary RQ job; expect finished and pong=true
docker compose exec -T backend python -m app.workers.enqueue ping --message demo --wait 30
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\demo_preflight.ps1 -FullTests -WorkerPing -StrictLogs
```

Health 200 chỉ chứng minh DB và Redis ở mức health probe. Không chứng minh OAuth, AI, ClamAV hoặc Worker đã thực hiện nghiệp vụ. Preflight exit 1 nếu có check FAIL; WARN/SKIP phải được xem xét và smoke test thủ công trước khi demo. Không dùng `docker compose down -v` khi còn dữ liệu. `docker compose down` giữ named volumes.

## 6. Kiểm thử / CI

Backend CI chạy Ruff check, Ruff format check, `pytest -m 'not integration'` với cấu hình test. Frontend chạy typecheck, lint, regression tests, build. Có CI PostgreSQL riêng cho Mentor/Roadmap và Gitleaks. Xem `.github/workflows/ci.yml`; integration tests sử dụng DB test tách biệt, không trỏ vào dữ liệu demo. Frontend `npm test` bao gồm evidence, roadmap, CV; CI còn chạy Dashboard, score presentation, analysis feedback và mentor proposal regressions.

## 7. Kiểm chứng dữ liệu và production

- [E2E evidence validation](docs/E2E_EVIDENCE_VALIDATION.md): đối chiếu GitHub, job, report, verification, score, Dashboard theo cùng report ID và SHA.
- [Production deployment](docs/PRODUCTION_DEPLOYMENT.md): cấu hình ứng viên production độc lập, HTTPS, secrets, backup, logging, checklist staging. Không tuyên bố đã triển khai production khi chưa nghiệm thu.
- [Frontend](frontend/README.md), [Worker](backend/app/workers/README.md), [Alembic](backend/migrations/README.md).

## 8. Luồng làm việc nhóm

Fetch và kiểm tra master; làm việc trên branch riêng; kiểm tra thay đổi và test; mở PR vào master; review và chỉ merge khi checks bắt buộc đạt. Không commit `.env`, GitHub token, AI key hoặc backup chứa dữ liệu riêng tư.

## 9. Ghi chú nghiệp vụ chi tiết

### Điểm vai trò theo phạm vi (PBI-018)

Đăng nhập và mở **Điểm năng lực theo vai trò** ở trang chính. Chọn vai trò
và phạm vi **Công khai**, **Riêng tư** hoặc **Kết hợp**. Riêng tư chỉ xuất hiện
khi tài khoản có repository được phép sử dụng với consent hiện hành.

- `GET /api/v1/role-scoring/roles/{role_key}/score/scoped` trả ba phạm vi
  riêng, cùng phiên bản rubric. Phản hồi yêu cầu phiên đăng nhập và dùng
  `Cache-Control: no-store`.
- Mỗi phạm vi sử dụng báo cáo gần nhất và điểm PBI-016 gắn với báo cáo đó.
  Snapshot ref được dẫn xuất từ ID của các bản ghi điểm, báo cáo và rubric.
- Confidence dựa trên bằng chứng đã liên kết hoặc phần confidence của PBI-016
  đã xác thực nguồn. Coverage là phần trọng số rubric có đủ bằng chứng.
  Khi dữ liệu thiếu, điểm là `null` và giao diện hiện **Chưa đủ bằng chứng**.
- Combined chạy lại rubric trên bằng chứng đã khử trùng. Bằng chứng kiến trúc
  cùng commit/vị trí chỉ tính một lần. Điểm skill có bộ evidence giống hệt
  chỉ đưa vào rubric một lần. Mỗi phạm vi giới hạn 50 repo theo giới hạn của
  provider và báo rõ nếu danh sách bị cắt.
- Kiểm thử có PostgreSQL riêng chạy bằng
  `RUN_INTEGRATION=1 pytest tests/modules/role_scoring/test_scoped_postgres.py`.
  Fixture tạo và xóa database tạm qua Alembic.

Đối chiếu SRS 2.0 FR-013 và FR-014. Endpoint chỉ đọc từ schema hiện hành.

### Dashboard hồ sơ và bằng chứng (PBI-019)

Mở **Dashboard hồ sơ** tại `/dashboard`. Chọn vai trò, phạm vi Công khai /
Riêng tư / Kết hợp và khoảng ngày UTC. Các thanh điểm lấy dữ liệu trực tiếp
từ API. Điểm vai trò và confidence cùng dùng thang 0–100; độ phủ được chuyển
từ tỷ lệ sang thang 0–100 khi hiển thị.

- Bộ lọc thời gian lấy báo cáo gần nhất theo ngày phân tích trong khoảng đã
  chọn, bao gồm cả hai ngày. Điểm kỹ năng và Finding dùng cùng ID báo cáo.
- Bằng chứng PR lấy từ báo cáo cộng tác gần nhất có sự kiện trong khoảng
  ngày đã chọn. Dùng ô **Số PR** để xem một PR cụ thể.
- Quyền repository và consent được kiểm tra trên server khi đọc báo cáo và
  bằng chứng. Trang **Tài khoản và kết nối GitHub** tại `/system-status`
  vẫn là nơi quản lý đồng bộ, kết nối và đăng xuất.
- Kiểm thử API với PostgreSQL riêng:
  `RUN_INTEGRATION=1 pytest tests/modules/role_scoring/test_dashboard_postgres.py`.
