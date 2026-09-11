"""Pydantic request/response models for auth — API Specification V1 §1.
WRITTEN, NOT EXECUTED."""
from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    username: str


class RegisterResponse(BaseModel):
    user_id: str


class VerifyEmailRequest(BaseModel):
    token: str


class VerifyEmailResponse(BaseModel):
    verified: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponseUser(BaseModel):
    id: str
    email: str
    name: str
    username: str


class LoginResponse(BaseModel):
    user: LoginResponseUser


class PasswordResetRequestRequest(BaseModel):
    email: EmailStr


class PasswordResetRequestResponse(BaseModel):
    sent: bool


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str


class PasswordResetConfirmResponse(BaseModel):
    reset: bool


class SessionResponse(BaseModel):
    user_id: str
    email: str
    roles: list[str]
    effective_tier: str
