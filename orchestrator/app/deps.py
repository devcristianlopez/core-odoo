"""FastAPI dependency providers."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from .config import Settings
from .models import Project, ProjectMember, User
from .providers.base import EnvironmentProvider
from .security import Principal, SecurityService

_bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_security(request: Request) -> SecurityService:
    return request.app.state.security


def get_provider(request: Request) -> EnvironmentProvider:
    return request.app.state.provider


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def require_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    principal = request.app.state.security.authenticate_token(credentials.credentials)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if principal.method == "jwt":
        user = session.exec(select(User).where(User.username == principal.username)).first()
        if user is None or not user.active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="user is inactive or missing",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return Principal(username=user.username, method="jwt", role=user.role)
    return principal


def require_write(request: Request, principal: PrincipalDep) -> Principal:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return principal
    if principal.role not in {"admin", "operator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this action requires operator or admin role",
        )
    return principal


def require_admin(principal: PrincipalDep) -> Principal:
    if principal.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this action requires admin role",
        )
    return principal


def require_project_access(
    request: Request,
    principal: PrincipalDep,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    name = request.path_params.get("name")
    if not name or principal.role == "admin" or principal.method == "api_token":
        return
    project = session.exec(select(Project).where(Project.name == name)).first()
    if project is None:
        return
    user = session.exec(select(User).where(User.username == principal.username)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="project access denied")
    membership = session.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
        )
    ).first()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="project access denied")


SettingsDep = Annotated[Settings, Depends(get_settings)]
SecurityDep = Annotated[SecurityService, Depends(get_security)]
ProviderDep = Annotated[EnvironmentProvider, Depends(get_provider)]
SessionDep = Annotated[Session, Depends(get_session)]
PrincipalDep = Annotated[Principal, Depends(require_principal)]
WritePrincipalDep = Annotated[Principal, Depends(require_write)]
AdminDep = Annotated[Principal, Depends(require_admin)]
