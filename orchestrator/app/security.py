"""Authentication: machine API token + short-lived JWTs for the panel."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import Settings


class AuthError(Exception):
    """Raised when credentials or tokens are invalid."""


@dataclass(frozen=True)
class Principal:
    username: str
    method: str  # "api_token" | "jwt"


class SecurityService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._hasher = PasswordHasher()
        self._admin_hash = self._hasher.hash(settings.core_admin_password)

    def verify_admin(self, username: str, password: str) -> bool:
        if not hmac.compare_digest(username, self._settings.core_admin_user):
            return False
        try:
            return self._hasher.verify(self._admin_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def issue_token(self, username: str) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": username,
            "iss": self._settings.core_jwt_issuer,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self._settings.core_jwt_ttl_minutes)).timestamp()),
        }
        return jwt.encode(payload, self._settings.core_jwt_secret, algorithm="HS256")

    def decode_token(self, token: str) -> str:
        try:
            payload = jwt.decode(
                token,
                self._settings.core_jwt_secret,
                algorithms=["HS256"],
                issuer=self._settings.core_jwt_issuer,
                options={"require": ["sub", "exp", "iat"]},
            )
        except jwt.PyJWTError as exc:  # noqa: BLE001 - normalised to AuthError
            raise AuthError("invalid or expired token") from exc
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise AuthError("invalid token subject")
        return subject

    def authenticate_token(self, token: str) -> Principal | None:
        if hmac.compare_digest(token, self._settings.core_api_token):
            return Principal(username="api", method="api_token")
        try:
            subject = self.decode_token(token)
        except AuthError:
            return None
        return Principal(username=subject, method="jwt")
