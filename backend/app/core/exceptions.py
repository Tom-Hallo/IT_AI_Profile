"""Ngoại lệ dùng chung của backend."""


class ConfigurationError(RuntimeError):
    """Cấu hình môi trường thiếu hoặc sai.

    Thông báo chỉ được chứa TÊN biến môi trường, tuyệt đối không chứa giá trị
    (giá trị có thể là mật khẩu hoặc URL kết nối).
    """
