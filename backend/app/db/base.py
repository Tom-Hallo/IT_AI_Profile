"""Lớp nền SQLAlchemy 2.x (Blueprint mục 1.4).

LƯU Ý BÀN GIAO: file này do Backend viết TẠM đúng hợp đồng 1.4 để health check chạy được.
Chủ sở hữu thật là Database Engineer (D1): có thể thay thế/mở rộng, giữ nguyên tên `Base`.
Chưa có model hay bảng nghiệp vụ nào.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
