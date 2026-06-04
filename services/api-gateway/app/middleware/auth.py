"""
JWT authentication middleware and dependency helpers.

Provides token creation, verification, role-based access control,
and FastAPI dependency injection utilities for securing endpoints.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Token creation helpers
# ---------------------------------------------------------------------------


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        data: Claims to embed in the token (must include ``sub``).
        expires_delta: Custom expiry duration.  Falls back to
            ``settings.access_token_expire_minutes`` when *None*.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta is not None else timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(data: dict[str, Any]) -> str:
    """
    Create a signed JWT refresh token with a longer lifespan.

    Args:
        data: Claims to embed (must include ``sub``).

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def verify_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT token.

    Args:
        token: Encoded JWT string.

    Returns:
        Decoded payload dictionary.

    Raises:
        HTTPException: 401 if the token is invalid or expired.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("sub") is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token does not contain a valid subject claim",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except JWTError as exc:
        logger.warning("jwt_verification_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------------
# FastAPI security dependencies
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer()


class JWTBearer:
    """
    FastAPI dependency that validates a Bearer JWT on every request.

    Usage::

        @router.get("/protected", dependencies=[Depends(JWTBearer())])
        async def protected_route(): ...
    """

    async def __call__(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    ) -> dict[str, Any]:
        """
        Validate the bearer token and return its decoded payload.

        Raises:
            HTTPException: 401/403 on authentication failure.
        """
        if credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid authentication scheme; expected Bearer",
            )

        payload = verify_token(credentials.credentials)

        # Reject refresh tokens used as access tokens
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type; expected access token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """
    Dependency that returns the current authenticated user payload.

    Returns:
        Decoded JWT payload containing user claims.
    """
    payload = verify_token(credentials.credentials)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type; expected access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def require_role(roles: list[str]):
    """
    Dependency factory that enforces role-based access control.

    Args:
        roles: List of roles that are permitted to access the endpoint.

    Returns:
        A FastAPI dependency coroutine.

    Usage::

        @router.get(
            "/admin-only",
            dependencies=[Depends(require_role(["admin"]))],
        )
        async def admin_endpoint(): ...
    """

    async def _role_checker(
        payload: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        user_roles: list[str] = payload.get("roles", [])
        if not any(role in user_roles for role in roles):
            logger.warning(
                "access_denied_insufficient_role",
                required=roles,
                actual=user_roles,
                user=payload.get("sub"),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {roles}",
            )
        return payload

    return _role_checker
