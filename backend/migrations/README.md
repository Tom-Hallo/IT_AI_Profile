# Migration cơ sở dữ liệu (Alembic)

Migration là các file Python ghi lại **từng thay đổi** của cấu trúc database (tạo bảng, thêm cột...),
theo thứ tự, để mọi thành viên và mọi môi trường có cùng một database. Thư mục này do Database
Engineer quản lý. PBI-001 mới chỉ có một revision **rỗng** tên `baseline`: nó không tạo bảng nào,
chỉ chứng minh chuỗi migration chạy được (Alembic tạo bảng hệ thống `alembic_version`).

## Các file liên quan

| File | Vai trò |
|---|---|
| `backend/alembic.ini` | Cấu hình Alembic. **Không chứa URL hay mật khẩu** |
| `backend/migrations/env.py` | Cách Alembic kết nối DB. Dùng `app.db.session.engine`, tức cùng cấu hình với Backend và Worker |
| `backend/migrations/versions/` | Các revision, tên file dạng `YYYYMMDD_HHMM_<id>_<mô tả>.py` |
| `backend/app/db/base.py` | `Base` cho model (đã đặt sẵn quy ước tên ràng buộc) |
| `backend/app/db/session.py` | `engine`, `get_session()`, `session_scope()`, `check_database()` |

URL kết nối chỉ đến từ biến môi trường `DATABASE_URL` (đọc qua `app/core/config.py`). Dạng bắt buộc:
`postgresql+psycopg://USER:MẬT_KHẨU@HOST:PORT/TÊN_DB`.

## Lệnh thường dùng

Chạy trong thư mục `backend/` (Alembic tìm `alembic.ini` ở thư mục hiện tại).

| Mục đích | Chạy ngoài Docker | Chạy trong Docker (khi đã có Compose) |
|---|---|---|
| **Áp dụng mọi migration** | `alembic upgrade head` | `docker compose exec backend alembic upgrade head` |
| Xem phiên bản DB đang ở | `alembic current` | `docker compose exec backend alembic current` |
| Xem lịch sử | `alembic history` | `docker compose exec backend alembic history` |
| Lùi một bước | `alembic downgrade -1` | `docker compose exec backend alembic downgrade -1` |
| Kiểm tra model có lệch migration không | `alembic check` | `docker compose exec backend alembic check` |
| Xem SQL mà không chạy (không cần DB) | `alembic upgrade head --sql` | |

Kết quả đúng khi mới cài: `alembic upgrade head` rồi `alembic current` in ra
`<mã revision> (head)`. Lưu ý **`alembic current` trên database mới tinh in ra trống và vẫn thoát mã 0**;
điều đó nghĩa là chưa áp dụng revision nào, không phải lỗi.

Chạy ngoài Docker cần: PostgreSQL đang chạy, file `backend/.env` (sao chép từ `backend/.env.example`,
host dùng `127.0.0.1`), và đã `pip install ".[dev]"` trong môi trường ảo.

> `downgrade` có thể **xóa dữ liệu** khi các revision sau này có bảng thật. Chỉ dùng trên database dev.

## Tạo migration mới (cho các PBI sau)

1. Tạo/sửa model kế thừa `app.db.base.Base`, rồi đảm bảo model được import trước khi Alembic đọc
   metadata (xem chú thích trong `env.py`). Hiện chưa có model nào.
2. `alembic revision --autogenerate -m "mô tả ngắn"` rồi **đọc lại file được sinh ra**.
   Autogenerate không phát hiện hết mọi thay đổi (ví dụ đổi tên cột sẽ bị hiểu là xóa rồi thêm).
3. `alembic upgrade head`, kiểm tra, rồi thử `alembic downgrade -1` và `upgrade head` lại.
4. Mỗi PR chỉ nên thêm **một** revision. Revision mới tự động được chạy qua `ruff` (cần dev dependency)
   để khớp lint của CI.
5. Không sửa revision đã được merge. Cần thay đổi thì thêm revision mới.

## Xử lý lỗi thường gặp

Thông báo lỗi kết nối của Alembic có thể ghi tên user, host và tên database, nhưng **không ghi mật khẩu**.
Dù vậy, đừng dán toàn bộ log lên nơi công khai.

| Thông báo (rút gọn) | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `DATABASE_URL (thiếu)` | Chưa có `backend/.env` (ngoài Docker) hoặc Compose không truyền biến | Sao chép `.env.example` thành `.env`, hoặc kiểm tra khối `environment:` của service |
| `DATABASE_URL (không hợp lệ)` | URL không bắt đầu bằng `postgresql+psycopg://` | Sửa thành đúng dạng. `postgresql://` và `postgres://` **không** được chấp nhận |
| `Connection refused` (kèm host/port) | PostgreSQL chưa chạy, hoặc sai port | Docker: `docker compose ps` xem `postgres` có `healthy` chưa. Ngoài Docker: bật PostgreSQL, kiểm tra port |
| `failed to resolve host 'postgres'` | Chạy **ngoài Docker** nhưng URL dùng tên host của Docker | Ngoài Docker dùng `127.0.0.1`. Tên `postgres` chỉ có hiệu lực **trong** mạng Compose |
| `password authentication failed for user` | Sai mật khẩu; hoặc đã đổi `POSTGRES_PASSWORD` sau khi volume DB được tạo (PostgreSQL chỉ áp dụng mật khẩu ở **lần khởi tạo đầu**) | Sửa lại cho khớp mật khẩu cũ, hoặc reset DB dev bằng `docker compose down -v` (**xóa toàn bộ dữ liệu**) |
| `database "..." does not exist` | Sai tên DB, hoặc đổi `POSTGRES_DB` sau khi volume đã tồn tại | Tương tự dòng trên |
| Kết nối vào "nhầm" PostgreSQL / lỗi mật khẩu dù đã đúng | Máy đã cài sẵn PostgreSQL chiếm port 5432 | Đổi `POSTGRES_HOST_PORT` (ví dụ 5433) và dùng port đó khi chạy ngoài Docker |
| `connection timeout expired` | Địa chỉ không tới được (firewall, sai host) | Kiểm tra host/port; ngoài Docker thử `127.0.0.1` thay vì `localhost` |
| `No 'script_location' key found` | Chạy lệnh `alembic` sai thư mục | `cd backend` rồi chạy lại |
| `No module named 'app'` | Chạy sai thư mục, hoặc chưa kích hoạt môi trường ảo | `cd backend`, kích hoạt `.venv` |
| `Can't locate revision identified by '...'` | DB đang ở revision mà code của bạn chưa có (nhánh cũ) | `git pull` / rebase từ `master` để lấy file revision còn thiếu |
| `Multiple head revisions are present` | Hai nhánh cùng thêm revision | `alembic heads` để xem, rồi `alembic merge heads -m "merge"`; báo Database Engineer |
| `alembic check` báo có thay đổi chưa có migration | Đã sửa model nhưng chưa tạo revision | Tạo revision mới (mục trên) |

Kiểm tra nhanh Backend có kết nối được PostgreSQL không: mở `GET /api/v1/health`, mục
`checks.database` phải là `ok`. Nếu `fail`, xem log của backend (log chỉ ghi **loại** lỗi, không ghi URL)
rồi đối chiếu bảng trên bằng cách chạy `alembic current` để thấy thông báo lỗi đầy đủ.

## Quy tắc

- Không đặt mật khẩu hay URL thật trong `alembic.ini`, `env.py` hay revision.
- Không tạo `create_engine` ở chỗ khác. Mọi nơi dùng `app.db.session.engine` (có test kiểm tra).
- PBI-001 **không** tạo bảng nghiệp vụ. Bảng đầu tiên sẽ đến cùng PBI nghiệp vụ tương ứng.
- Chạy migration là thao tác **thủ công**, không tự chạy khi khởi động container.
