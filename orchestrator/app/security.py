"""Authentication: local panel users, machine API token and JWTs."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlmodel import Session, select

from .config import Settings
from .models import User


class AuthError(Exception):
    """Raised when credentials or tokens are invalid."""


@dataclass(frozen=True)
class Principal:
    username: str
    method: str  # "api_token" | "jwt"
    role: str = "viewer"


class SecurityService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._hasher = PasswordHasher()

    def hash_password(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify_password(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def ensure_admin(self, session: Session) -> User:
        """Create the first admin from .env when the users table is empty."""
        existing = session.exec(
            select(User).where(User.username == self._settings.core_admin_user)
        ).first()
        if existing is not None:
            return existing
        admin = User(
            username=self._settings.core_admin_user,
            password_hash=self.hash_password(self._settings.core_admin_password),
            role="admin",
            active=True,
        )
        session.add(admin)
        session.commit()
        session.refresh(admin)
        return admin

    def authenticate(self, session: Session, username: str, password: str) -> User | None:
        user = session.exec(select(User).where(User.username == username)).first()
        if user is None or not user.active:
            return None
        return user if self.verify_password(user.password_hash, password) else None

    def issue_token(self, username: str, role: str) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": username,
            "role": role,
            "iss": self._settings.core_jwt_issuer,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self._settings.core_jwt_ttl_minutes)).timestamp()),
        }
        return jwt.encode(payload, self._settings.core_jwt_secret, algorithm="HS256")

    def decode_token(self, token: str) -> tuple[str, str]:
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
        role = payload.get("role", "viewer")
        if not isinstance(subject, str) or not subject:
            raise AuthError("invalid token subject")
        if role not in {"admin", "operator", "viewer"}:
            role = "viewer"
        return subject, role

    def authenticate_token(self, token: str) -> Principal | None:
        if hmac.compare_digest(token, self._settings.core_api_token):
            return Principal(username="api", method="api_token", role="admin")
        try:
            subject, role = self.decode_token(token)
        except AuthError:
            return None
        return Principal(username=subject, method="jwt", role=role)
