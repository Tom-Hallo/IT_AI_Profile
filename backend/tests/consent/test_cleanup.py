import sys
import uuid

import pytest

from app.modules.consent import cleanup


def test_purge_does_not_follow_symlink(tmp_path, monkeypatch):
    """Đảm bảo cleanup không xóa dữ liệu bên ngoài qua symbolic link."""

    monkeypatch.setattr(cleanup, "ROOT", tmp_path)

    # Tạo thư mục bên ngoài thư mục job
    outside = tmp_path.parent / ("outside-" + uuid.uuid4().hex)
    outside.mkdir()

    try:
        # File bên ngoài phải được bảo vệ
        protected_file = outside / "keep.txt"
        protected_file.write_text("keep", encoding="utf-8")

        # Tạo symbolic link trỏ ra ngoài thư mục job
        link = cleanup.job_directory(uuid.uuid4())

        try:
            link.symlink_to(outside, target_is_directory=True)

        except OSError as exc:
            # Windows có thể không cho phép tạo symbolic link
            if sys.platform == "win32" and getattr(exc, "winerror", None) == 1314:
                pytest.skip("Windows requires symlink privileges")

            # Lỗi khác phải được báo, không được bỏ qua
            raise

        # Gọi chức năng cleanup thực tế
        cleanup.purge_job_directory(link.name)

        # Kiểm tra file bên ngoài không bị xóa
        assert protected_file.exists()
        assert protected_file.read_text(encoding="utf-8") == "keep"

    finally:
        # Dọn dẹp dữ liệu test
        if outside.exists():
            protected_file = outside / "keep.txt"
            if protected_file.exists():
                protected_file.unlink()
            outside.rmdir()
