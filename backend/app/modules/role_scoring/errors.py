"""Lỗi miền của lớp tích hợp Role Scoring. Router ánh xạ sang HTTP."""

from __future__ import annotations


class RoleScoringError(Exception):
    """Gốc của mọi lỗi miền PBI-017."""


class RepositoryNotFoundError(RoleScoringError):
    """Repository không tồn tại hoặc không thuộc người dùng (không phân biệt)."""


class PrivateConsentRequiredError(RoleScoringError):
    """Repository private thiếu/đã thu hồi consent hoặc chưa bật private access."""


class SkillSnapshotSourceError(RoleScoringError):
    """Nguồn skill snapshot (PBI-016) lỗi hạ tầng, không được coi là thiếu dữ liệu."""


class SkillSnapshotSourceNotConfigured(RoleScoringError):
    """PBI-016 chưa được nối vào adapter."""
