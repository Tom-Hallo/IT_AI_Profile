"""Prompt templates và quy tắc bảo mật."""

from app.ai.prompts.security import (
    SYSTEM_SECURITY_INSTRUCTIONS,
    build_secure_input,
)

__all__ = [
    "SYSTEM_SECURITY_INSTRUCTIONS",
    "build_secure_input",
]
