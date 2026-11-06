# Hướng dẫn khởi động môi trường phát triển (Docker Compose)

Tài liệu của DevOps. Mô tả cách chạy 5 service (`frontend`, `backend`, `worker`, `postgres`, `redis`) bằng một cấu hình thống nhất.
Hợp đồng chi tiết nằm trong Technical Blueprint (mục 3, 5, 6). **Môi trường này chỉ dành cho phát triển**, không dùng cho staging/production.

## 1. Cần cài trước

| Thứ cần | Ghi chú |
|---|---|
| Docker Desktop (Windows/macOS) hoặc Docker Engine (Linux) | Cần **Docker Compose v2** (lệnh `docker compose`, có dấu cách) |
| Git | |

Windows: nên clone repo **bên trong WSL2** (ví dụ `~/projects`) để hot-reload nhanh và ổn định. Clone ở ổ `C:\...` vẫn chạy được nhưng xem mục 7 (hot-reload).

## 2. Chạy lần đầu

Chạy từ thư mục gốc repo. Script tự làm 4 việc: tạo `.env` từ `.env.example` (**không bao giờ ghi đè** `.env` có sẵn), kiểm tra Docker đang chạy, chạy `docker compose up -d --build --wait`, in địa chỉ truy cập.

| Hệ điều hành | Lệnh |
|---|---|
| Linux / macOS / WSL | `./scripts/setup.sh` |
| Windows PowerShell | `.\scripts\setup.ps1` (nếu bị chặn: `powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1`) |

Hoặc làm tay:

```bash
cp .env.example .env                     # PowerShell: Copy-Item .env.example .env
docker compose up -d --build --wait
```

Lần đầu mất vài phút (tải image, cài thư viện). `--wait` chỉ trả về mã 0 khi **cả 5 service** đã `healthy`.

## 3. Địa chỉ truy cập (từ máy của bạn)

| Mục | Địa chỉ | Ghi chú |
|---|---|---|
| Giao diện | http://localhost:5173 | Trang trạng thái hệ thống |
| API health | http://localhost:8000/api/v1/health | Kỳ vọng 200, `database: ok`, `redis: ok` |
| Swagger | http://localhost:8000/api/v1/docs | Chỉ khi `APP_ENV=development` |
| PostgreSQL | `127.0.0.1:5432` | Cho công cụ DB trên máy bạn. User/mật khẩu/DB lấy từ `.env` |
| Redis | `127.0.0.1:6379` | Để debug |

Mọi port chỉ gắn vào `127.0.0.1` (máy khác trong mạng LAN **không** truy cập được). Đổi port host bằng `FRONTEND_PORT`, `BACKEND_PORT`, `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT` trong `.env` rồi chạy lại `docker compose up -d`.

## 4. Lệnh hằng ngày

| Mục đích | Lệnh |
|---|---|
| Chạy (đã build rồi) | `docker compose up -d` |
| Build lại và chạy, đợi tới khi healthy | `docker compose up -d --build --wait` |
| Xem trạng thái | `docker compose ps` |
| Xem log | `docker compose logs -f <service>` (ví dụ `backend`) |
| Dừng, **giữ** dữ liệu DB | `docker compose down` |
| Reset hoàn toàn, **XÓA dữ liệu DB** | `docker compose down -v` |
| Khởi động lại một service | `docker compose restart <service>` (sau khi sửa code **worker** bắt buộc làm vậy, worker không hot-reload) |
| Migration | `docker compose exec backend alembic upgrade head` (không tự chạy khi khởi động) |
| Test backend | `docker compose exec backend pytest` |
| Lint / typecheck / build frontend | `docker compose exec frontend npm run lint` / `typecheck` / `build` |
| Đưa job mẫu vào hàng đợi và chờ kết quả | `docker compose exec backend python -m app.workers.enqueue ping --wait 20` |
| Mở shell trong service | `docker compose exec backend bash` (frontend: `sh`) |

## 5. Các service gọi nhau thế nào (localhost khác nhau giữa máy bạn và container)

- **Từ máy bạn** (trình duyệt, DBeaver, `redis-cli`): dùng `localhost` hoặc `127.0.0.1` cùng port host ở mục 3.
- **Giữa các container**: dùng **tên service** và port trong container, **không** dùng `localhost`. Trong container `localhost` là chính container đó.

| Biến | Giá trị trong Docker | Do ai đặt |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://<user>:<mật khẩu>@postgres:5432/<db>` | Compose tự ghép từ `POSTGRES_*` |
| `REDIS_URL` | `redis://redis:6379/0` | Compose |
| `BACKEND_INTERNAL_URL` | `http://backend:8000` | `.env` (chỉ phía Node của Vite) |
| `VITE_API_BASE_URL` | `/api/v1` | `.env` (trình duyệt gọi cùng origin, Vite chuyển tiếp tới backend) |

`DATABASE_URL` và `REDIS_URL` **không** nằm trong `.env`. File `backend/.env.example` và `frontend/.env.example` (trỏ `127.0.0.1`) chỉ dùng khi chạy **ngoài** Docker.

## 6. Thứ tự khởi động và healthcheck

```
postgres (healthy) ─┐
                    ├─> backend (healthy) ... worker (healthy)
redis    (healthy) ─┘
frontend: không phụ thuộc cứng vào backend (trang trạng thái tự báo lỗi nếu backend chưa lên)
```

| Service | Healthcheck | Khỏe khi |
|---|---|---|
| `postgres` | `pg_isready -h 127.0.0.1 ...` | Nhận kết nối TCP |
| `redis` | `redis-cli ping` | Trả `PONG` |
| `backend` | `GET /api/v1/health` bằng python | HTTP 200 (503 khi DB hoặc Redis lỗi thì **không** khỏe) |
| `worker` | lệnh python trong `docker-compose.yml` | Kết nối được Redis **và** có worker RQ đang chạy trong chính container này |
| `frontend` | `wget http://127.0.0.1:5173/` | Vite trả trang |

Backend và worker chỉ khởi động sau khi `postgres` và `redis` **healthy**, nên không có chuyện backend chạm DB khi DB chưa sẵn sàng.

## 7. Lỗi thường gặp

| Triệu chứng | Nguyên nhân / cách xử lý |
|---|---|
| `required variable ... is missing a value` | Chưa có `.env` hoặc thiếu biến. Chạy `cp .env.example .env` (thông báo chỉ nêu **tên** biến, không nêu giá trị) |
| `port is already allocated` / `address already in use` | Port host bị chiếm (thường là PostgreSQL 5432 cài sẵn). Đổi `*_PORT` tương ứng trong `.env` |
| `Cannot connect to the Docker daemon` | Docker chưa chạy. Mở Docker Desktop |
| `password authentication failed for user` | Bạn đổi `POSTGRES_PASSWORD`/`POSTGRES_USER`/`POSTGRES_DB` **sau khi** volume đã tạo (giá trị chỉ có tác dụng lần đầu). Hoặc trả lại giá trị cũ, hoặc `docker compose down -v` (**xóa dữ liệu**) |
| Mật khẩu có ký tự `@ : / ? # %` làm backend báo lỗi cấu hình | Chỉ dùng chữ, số, `-`, `_` cho `POSTGRES_PASSWORD` |
| Sửa code frontend/backend không tự cập nhật trên Windows | Đặt `FRONTEND_WATCH_POLLING=true` trong `.env` (frontend). Tốt nhất clone trong WSL2 |
| Đổi `pyproject.toml` hoặc `package.json` mà không có tác dụng | Thư viện nằm trong image: `docker compose build backend` (hoặc `frontend`). Với frontend thêm `docker compose up -d --renew-anon-volumes frontend` vì `node_modules` nằm trong volume ẩn |
| Backend `healthy` nhưng `worker` không | `docker compose logs worker`. Sau khi sửa code worker phải `docker compose restart worker` |
| `exec ./scripts/setup.sh: bad interpreter` hoặc `\r` | File bị đổi sang CRLF. `.gitattributes` đã ép LF; chạy `git add --renormalize .` hoặc clone lại |
| Thư mục `frontend/node_modules` rỗng xuất hiện trên máy | Bình thường: Docker tạo điểm mount cho volume ẩn. Đã nằm trong `.gitignore` |

## 8. Kiểm thử thủ công (dùng cho QA)

Chạy sau `docker compose up -d --build --wait`. Mỗi ca ghi PASS/FAIL/NOT RUN kèm bằng chứng.

| # | Việc | Lệnh | Kỳ vọng |
|---|---|---|---|
| 1 | Build | `docker compose build` | Thoát mã 0 |
| 2 | Khởi động | `docker compose up -d --build --wait; echo $?` | Mã 0 |
| 3 | Trạng thái | `docker compose ps` | 5 service `healthy` |
| 4 | Frontend | `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/` rồi mở trình duyệt | 200, trang trạng thái hiển thị `ok` |
| 5 | Health backend | `curl -s http://localhost:8000/api/v1/health` | 200, `database: ok`, `redis: ok` |
| 6 | Backend ↔ PostgreSQL | `docker compose exec backend alembic upgrade head` rồi `docker compose exec backend alembic current` | in `fe534ebbefc6 (head)` |
| 7 | Job và worker | `docker compose exec backend python -m app.workers.enqueue ping --wait 20` | mã 0, `"status": "finished"`, `"pong": true` |
| 8 | Giữ dữ liệu DB | tạo bảng thử (xem dưới), `docker compose down`, `docker compose up -d --wait`, đọc lại | dữ liệu còn nguyên |
| 9 | Thiếu biến | `mv .env .env.bak; docker compose config -q; mv .env.bak .env` | lỗi nêu tên biến (`APP_ENV`, `POSTGRES_*`...), không nêu giá trị |

Ca 8:

```bash
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE TABLE qa_probe(x int); INSERT INTO qa_probe VALUES (42);"'
docker compose down && docker compose up -d --wait
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT * FROM qa_probe;"'   # phải thấy 42
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP TABLE qa_probe;"'      # dọn
```

Thêm (T3, T4 của Blueprint): `docker compose stop postgres` → health 503, `database: fail`; `docker compose start postgres` → về 200. `docker compose stop redis` → health 503 và worker `unhealthy`; `docker compose start redis` → phục hồi.

## 9. Vấn đề còn tồn tại (DevOps ghi nhận)

1. **Chưa có `python -m app.workers.healthcheck`.** Blueprint (mục 1.4, 3) quy định module này nhưng Worker chưa tạo. Compose tạm dùng lệnh python nằm trong `docker-compose.yml`. Cần Worker thêm module rồi đổi dòng `healthcheck` của `worker`.
2. **Tên task:** Blueprint 4.3 ghi `app.workers.tasks.system.ping`, repo có `app.workers.tasks.ping.ping`. Lệnh enqueue ở mục 4 dùng bản trong repo.
3. **Healthcheck worker không phát hiện worker bị treo** (còn sống nhưng không xử lý job); chỉ phát hiện worker chết hoặc mất Redis.
4. **Chưa kiểm chứng trong Docker thật** các điểm ghi NOT RUN ở handoff: build image, `up --wait` đủ 5 service, `wget` trong `node:24-alpine`, quyền ghi bind mount trên Linux (uid 1000), hot-reload trên Windows.
5. `frontend/.gitignore` còn dư so với `.gitignore` gốc (vô hại).
