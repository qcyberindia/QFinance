"""
FastAPI app factory (Architecture §4.1 `main.py`).
WRITTEN, NOT EXECUTED — `uvicorn app.main:app` has not been run in this session.
"""
from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import QFinanceAPIError, qfinance_error_handler, unhandled_exception_handler

settings = get_settings()

app = FastAPI(title="QFinance API", version="1.0.0")

app.add_exception_handler(QFinanceAPIError, qfinance_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
