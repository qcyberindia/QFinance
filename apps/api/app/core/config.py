"""
QFinance API — application configuration.
Derived from Architecture V1 §3/§13 (secrets via environment, never committed) and
API Specification V1 §0 (session/CSRF cookie names).
WRITTEN, NOT EXECUTED in this session — no Python interpreter has run this file.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # Database (Architecture §3, §5)
    DATABASE_URL: str = "postgresql+asyncpg://qfinance:qfinance@localhost:5432/qfinance"

    # Redis (Architecture §3, AD-03/AD-07)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Session / CSRF cookies (API Spec §0.2, Architecture AD-03/AD-14)
    SESSION_COOKIE_NAME: str = "qf_session"
    CSRF_COOKIE_NAME: str = "csrf_token"
    SESSION_TTL_SECONDS: int = 60 * 60 * 24 * 30  # 30 days, server-side revocable (AD-03)

    # Password policy (OD-03)
    PASSWORD_MIN_LENGTH: int = 12

    # BOUND-003 paid-launch gate (API Spec §3.2.1/§10.9). Must remain False until
    # OD-01 legal/regulatory sign-off; only ever read from env/config here, never
    # hardcoded True, and never flipped by this codebase itself.
    CORE_BILLING_ENABLED: bool = False

    # Provider abstractions (Architecture §4.4, OD-10/11/12) — names only, no values.
    RAZORPAY_KEY_ID: str | None = None
    RAZORPAY_KEY_SECRET: str | None = None
    RAZORPAY_WEBHOOK_SECRET: str | None = None
    RESEND_API_KEY: str | None = None
    AWS_S3_BUCKET: str | None = None
    AWS_REGION: str = "ap-south-1"  # OD-18 — infrastructure preference, not a legal claim

    # Compliance document versions (CMPL-004/005, API Spec §4.5.1/§4.5.2, Database
    # Schema §8A `compliance_acknowledgments.document_version`). A config value, not
    # a hardcoded literal in service.py, so a future Charter/disclosure text update
    # only requires bumping this string — every acknowledgment row still records
    # exactly which version a member actually acknowledged, per AD-16's reasoning.
    MEMBER_CHARTER_VERSION: str = "v1"
    RISK_DISCLOSURE_VERSION: str = "v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
