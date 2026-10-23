"""JWT issuing/verification for the gateway."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from .config import AuthConfig


class TokenError(Exception):
    """Invalid or expired token."""


class TokenService:
    def __init__(self, config: AuthConfig) -> None:
        self._config = config

    def issue(self, login: str) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": login,
            "iss": self._config.issuer,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self._config.jwt_ttl_minutes)).timestamp()),
        }
        secret = self._config.jwt_secret or "gateway-auth-disabled"
        return jwt.encode(payload, secret, algorithm="HS256")

    def verify(self, token: str) -> str:
        secret = self._config.jwt_secret
        if not secret:
            raise TokenError("gateway auth is not configured")
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                issuer=self._config.issuer,
                options={"require": ["sub", "exp", "iat"]},
            )
        except jwt.PyJWTError as exc:
            raise TokenError("invalid or expired token") from exc
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise TokenError("invalid token subject")
        return subject
