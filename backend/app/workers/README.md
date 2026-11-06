# Worker: xử lý tác vụ nền (Redis + RQ)

Mọi lệnh chạy trong thư mục `backend/`, đã kích hoạt venv và đã có `backend/.env`
(sao chép từ `backend/.env.example`). Cần có Redis đang chạy tại `REDIS_URL`.

## 1. Bật Redis (chạy ngoài Docker Compose)

```powershell
docker run -d --name redis-dev -p 127.0.0.1:6379:6379 redis:8
```

Trong `backend/.env`: `REDIS_URL=redis://127.0.0.1:6379/0` (dùng `127.0.0.1`, không dùng `localhost`).

## 2. Chạy worker

```powershell
python -m app.workers.worker            # chạy liên tục, Ctrl+C để dừng
python -m app.workers.worker --burst    # xử lý hết job đang chờ rồi thoát (dùng khi test)
```

- Hàng đợi lấy từ `WORKER_QUEUES` (mặc định `default`, nhiều hàng đợi cách nhau bằng dấu phẩy).
- Redis không kết nối được: worker ghi một dòng lỗi (chỉ tên loại lỗi) và thoát với mã 1.
- Dừng bằng Ctrl+C hoặc SIGTERM là dừng "êm": chờ job đang chạy xong.

> **Windows gốc:** RQ không hỗ trợ chính thức. Worker tự chuyển sang `SimpleWorker` (job chạy ngay
> trong tiến trình worker). Chỉ dùng để phát triển và **chưa được chạy thử trên Windows thật**.
> Môi trường chuẩn là Docker/Linux (dùng `Worker` mặc định, mỗi job một tiến trình con).

## 3. Đưa job vào hàng đợi (enqueue)

Từ dòng lệnh:

```powershell
python -m app.workers.enqueue ping --message "xin chao"            # in ra job_id, status=queued
python -m app.workers.enqueue ping --message "xin chao" --wait 15  # chờ tối đa 15 giây cho worker xong
```

Từ code Backend:

```python
from app.workers.enqueue import enqueue_ping, enqueue_task

job = enqueue_ping("xin chao")  # job mẫu
job = enqueue_task(my_task, 42)  # job mới: tham số chỉ là kiểu JSON đơn giản
print(job.id)
```

## 4. Kiểm tra kết quả

```powershell
python -m app.workers.enqueue status <job_id>
```

Kết quả mẫu: `{"job_id": "...", "queue": "default", "status": "finished", "result": {"pong": true, ...}}`.
Trạng thái: `queued` (đang chờ) → `started` → `finished` hoặc `failed`.
Kết quả giữ 1 giờ; job lỗi giữ 24 giờ (hằng số trong `queues.py`). Hết hạn thì báo không tìm thấy job.

Mã thoát của `ping --wait`: 0 xong, 1 lỗi, 2 hết thời gian chờ.

## 5. Chứng minh quy trình bằng test

```powershell
pytest tests/workers                           # test đơn vị, không cần Redis
$env:RUN_INTEGRATION="1"; pytest tests/workers # tích hợp: enqueue -> Redis -> worker -> finished
```

(Linux/macOS: `RUN_INTEGRATION=1 pytest tests/workers`.)

## 6. Thêm job mới

1. Tạo hàm trong `app/workers/tasks/<ten>.py`: tham số và kết quả là kiểu JSON đơn giản.
2. Cần DB thì mở session **bên trong** hàm bằng `from app.db.session import session_scope`.
   Không tạo engine riêng; không truy cập DB ở `worker.py`.
3. Enqueue bằng `enqueue_task(ham, ...)` để thời hạn và serializer luôn nhất quán.

## 7. Lưu ý an toàn

- **Không đưa secret, token, URL kết nối vào tham số job.** RQ ghi tên hàm và tham số của job vào
  log và vào Redis. `RedactingFilter` chỉ che thông điệp log, không che traceback.
- Worker chỉ ghi `job id`, tên hàm và **loại** lỗi khi job hỏng; traceback đầy đủ nằm ở job lỗi trong Redis.
- Serializer là JSON ở cả hai phía; không dùng pickle.
- Redis chỉ nên mở ở `127.0.0.1` (hoặc mạng nội bộ Docker); không công khai cổng 6379.

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân / cách xử lý |
|---|---|
| `Khong ket noi duoc Redis (ConnectionError)` | Redis chưa chạy hoặc sai `REDIS_URL`. Kiểm tra `docker ps`. |
| Job mãi `queued` | Chưa có worker, hoặc worker nghe hàng đợi khác. Đối chiếu `WORKER_QUEUES`. |
| `failed` | Xem log worker (loại lỗi), hoặc `Job.fetch(...).latest_result()` để xem chi tiết. |
| `Khong tim thay job` | Sai id hoặc đã hết hạn lưu. |
| Cấu hình môi trường chưa đúng | Thiếu `APP_ENV`, `DATABASE_URL`, `REDIS_URL` trong `backend/.env`. |
