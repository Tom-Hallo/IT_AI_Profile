"""Các hàm job của worker.

Quy ước:
- Tham số là kiểu JSON đơn giản (id, chuỗi, số). Không truyền secret, URL kết nối, đối
tượng.
- Job cần DB thì tự mở session riêng bằng `app.db.session.session_scope()` BÊN TRONG hàm
job;
  không tạo engine riêng và không truy cập DB ở tiến trình worker cha.
- Giá trị trả về phải là kiểu JSON (dict, list, chuỗi, số, bool, None).
"""
