"""Lớp nền SQLAlchemy 2.x (Blueprint mục 1.4).

Chủ sở hữu: Database Engineer (D1). Backend đã viết bản đầu (tạm) theo hợp đồng 1.4;
tên `Base` được giữ nguyên.

Chưa có model hay bảng nghiệp vụ nào trong PBI-001. Mọi model sau này kế thừa `Base`.

Quy ước đặt tên ràng buộc (naming convention):
    Đặt từ bây giờ, TRƯỚC khi có bảng đầu tiên. Nếu không, PostgreSQL tự sinh tên ràng buộc
    ngẫu nhiên và các migration sau này (drop/alter constraint) sẽ không tham chiếu được
    bằng tên ổn định. Đổi quy ước khi đã có bảng là việc rất tốn công.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
