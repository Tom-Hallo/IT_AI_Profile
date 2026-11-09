"""Integration adapter: replace with existing project's authenticated dependencies.
Fail closed: no placeholder authentication is provided.
"""
from fastapi import HTTPException

async def get_db():
    raise HTTPException(503, 'Configure existing PostgreSQL session dependency')

async def get_current_user_id():
    raise HTTPException(401, 'Configure existing JWT authentication dependency')
