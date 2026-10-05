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

    # Portfolio / Zerodha (Architecture V2 §3, PF.1–PF.4). Read-only Kite Connect
    # integration — never used for order placement (BOUND-001, reaffirmed for V2 in
    # the founder's explicit approval of read-only broker connectivity). If unset,
    # the connect flow returns a clean BROKER_NOT_CONFIGURED error rather than
    # crashing the application — mirrors the existing RAZORPAY_KEY_ID-unset pattern.
    ZERODHA_API_KEY: str | None = None
    ZERODHA_API_SECRET: str | None = None

    # Compliance document versions (CMPL-004/005, API Spec §4.5.1/§4.5.2, Database
    # Schema §8A `compliance_acknowledgments.document_version`). A config value, not
    # a hardcoded literal in service.py, so a future Charter/disclosure text update
    # only requires bumping this string — every acknowledgment row still records
    # exactly which version a member actually acknowledged, per AD-16's reasoning.
    MEMBER_CHARTER_VERSION: str = "v1"
    RISK_DISCLOSURE_VERSION: str = "v1"

    # Frontend base URL (Architecture §4.3's route-guard boundary) — used only to
    # build verification/password-reset links (AUTH-002/005); the backend doesn't
    # own frontend routing, but a link has to point somewhere real, and hardcoding
    # a literal in auth/service.py would silently break in any non-local deployment.
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # BYOK AI research assistant (research_ai module). The member's OWN AI provider
    # API key is encrypted at rest with this secret (Fernet/AES-128-CBC+HMAC via the
    # `cryptography` package) before ever reaching the database — Qfinera never
    # provides/hardcodes an AI key of its own. If unset, a random key is generated
    # at process start as a dev-safe fallback (existing encrypted keys from a prior
    # run become undecryptable if the process restarts without a fixed secret set —
    # acceptable for MVP/dev, NOT for any real deployment, which must set a fixed,
    # persisted secret via environment variable).
    AI_KEY_ENCRYPTION_SECRET: str | None = None
    # Encrypts stored broker (Zerodha) access tokens — separate from AI keys.
    # Required to connect a broker. Tokens written before this key existed
    # (under AI_KEY_ENCRYPTION_SECRET) are still read once and re-encrypted
    # under this key (see app/core/crypto.py). Never logged.
    BROKER_TOKEN_ENCRYPTION_SECRET: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
