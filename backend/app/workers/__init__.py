"""Nền tảng xử lý tác vụ nền (Redis + RQ), Task 06.

Cấu trúc:
- queues.py   : cấu hình hàng đợi RQ (kết nối, serializer, thời hạn lưu). Chủ sở hữu duy nhất.
- enqueue.py  : đưa job vào hàng đợi (dùng được từ Backend hoặc dòng lệnh).
- worker.py   : tiến trình worker (`python -m app.workers.worker`).
- tasks/      : các hàm job. Mỗi job là một hàm nhận tham số JSON đơn giản.

Xem README.md trong thư mục này để biết cách chạy.
"""
