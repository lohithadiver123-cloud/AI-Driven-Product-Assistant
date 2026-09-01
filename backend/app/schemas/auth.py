"""Authentication token and recovery request schemas."""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from app.schemas.user import UserProfileResponse


class TokenResponse(BaseModel):
    """Successful authentication response payload."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfileResponse


class RefreshTokenRequest(BaseModel):
    """Schema for refreshing access tokens."""

    refresh_token: str = Field(..., min_length=1)


class ForgotPasswordRequest(BaseModel):
    """Schema for initiating password recovery."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Schema for consuming a password reset token."""

    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)


class VerifyEmailRequest(BaseModel):
    """Schema for email verification."""

    token: str = Field(..., min_length=1)


class ResendVerificationRequest(BaseModel):
    """Schema for requesting a new verification email."""

    email: EmailStr
