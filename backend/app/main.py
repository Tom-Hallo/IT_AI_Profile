from fastapi import FastAPI
from app.api.activity import router
app = FastAPI(title='IT Talent AI Profile - PBI-010')
app.include_router(router)
