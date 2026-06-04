"""
Pydantic models for authentication request/response schemas.

These models define the data contracts for login, token refresh,
logout, and user information endpoints.
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Schema for user login request."""

    username: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Username for authentication",
        examples=["admin"],
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="User password",
        examples=["admin123"],
    )


class TokenResponse(BaseModel):
    """Schema for JWT token response after successful authentication."""

    access_token: str = Field(
        ...,
        description="JWT access token for API authorisation",
    )
    refresh_token: str = Field(
        ...,
        description="JWT refresh token used to obtain a new access token",
    )
    token_type: str = Field(
        default="bearer",
        description="Token type, always 'bearer'",
    )
    expires_in: int = Field(
        ...,
        description="Access token lifetime in seconds",
    )


class UserInfo(BaseModel):
    """Schema representing authenticated user information."""

    id: str = Field(..., description="Unique user identifier")
    username: str = Field(..., description="Login username")
    email: str = Field(..., description="User email address")
    roles: list[str] = Field(
        default_factory=list,
        description="Roles assigned to the user",
    )


class RefreshRequest(BaseModel):
    """Schema for token refresh request."""

    refresh_token: str = Field(
        ...,
        description="The refresh token to exchange for a new access token",
    )
