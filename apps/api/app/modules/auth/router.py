"""
Auth routes — API Specification V1 §1. Thin; delegates to service.py (Architecture §4.1).
WRITTEN, NOT EXECUTED.
"""
from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user, require_csrf
from app.core.security import generate_csrf_token
from app.modules.auth import service
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    LoginRequest, LoginResponse, LoginResponseUser,
    PasswordResetConfirmRequest, PasswordResetConfirmResponse, PasswordResetRequestRequest, PasswordResetRequestResponse,
    RegisterRequest, RegisterResponse, SessionResponse, VerifyEmailRequest, VerifyEmailResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user = await service.register(db, email=body.email, password=body.password, name=body.name, username=body.username)
    return RegisterResponse(user_id=str(user.id))


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    await service.verify_email(db, token=body.token)
    return VerifyEmailResponse(verified=True)


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user, session_token = await service.login(db, email=body.email, password=body.password)
    csrf_token = generate_csrf_token()
    response.set_cookie(
        settings.SESSION_COOKIE_NAME, session_token,
        httponly=True, secure=True, samesite="lax", max_age=settings.SESSION_TTL_SECONDS,
    )
    response.set_cookie(
        settings.CSRF_COOKIE_NAME, csrf_token,
        httponly=False, secure=True, samesite="lax", max_age=settings.SESSION_TTL_SECONDS,
    )
    return LoginResponse(user=LoginResponseUser(id=str(user.id), email=user.email, name="", username=""))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
async def logout(response: Response, qf_session: str | None = Cookie(default=None)):
    if qf_session:
        await service.logout(qf_session)
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    response.delete_cookie(settings.CSRF_COOKIE_NAME)


@router.post("/password-reset/request", response_model=PasswordResetRequestResponse)
async def password_reset_request(body: PasswordResetRequestRequest, db: AsyncSession = Depends(get_db)):
    await service.request_password_reset(db, email=body.email)
    return PasswordResetRequestResponse(sent=True)  # Always 200 — never reveals whether the email exists (API Spec §1.5)


@router.post("/password-reset/confirm", response_model=PasswordResetConfirmResponse)
async def password_reset_confirm(body: PasswordResetConfirmRequest, db: AsyncSession = Depends(get_db)):
    await service.confirm_password_reset(db, token=body.token, new_password=body.new_password)
    return PasswordResetConfirmResponse(reset=True)


@router.get("/session", response_model=SessionResponse)
async def session(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.modules.users.models import Profile
    profile = await db.get(Profile, user.id)
    roles = profile.role_grants if profile else []
    effective_tier = "CORE" if "MEMBER" in roles else "FREE"
    return SessionResponse(user_id=str(user.id), email=user.email, roles=roles, effective_tier=effective_tier)
