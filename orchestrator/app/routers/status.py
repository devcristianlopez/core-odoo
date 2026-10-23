"""Control-plane status endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func
from sqlmodel import select

from .. import __version__
from ..deps import PrincipalDep, ProviderDep, SessionDep
from ..models import Environment
from ..schemas import DiskStatus, DockerStatus, StatusResponse

router = APIRouter(tags=["status"])


@router.get("/status", response_model=StatusResponse)
def status(
    session: SessionDep,
    principal: PrincipalDep,
    provider: ProviderDep,
) -> StatusResponse:
    info = provider.docker_info()
    disk = provider.disk_info()
    environment_count = session.exec(select(func.count()).select_from(Environment)).one()
    return StatusResponse(
        docker=DockerStatus(available=info.available, version=info.version, error=info.error),
        disk=DiskStatus(
            total_gb=disk.total_gb,
            used_gb=disk.used_gb,
            free_gb=disk.free_gb,
            percent=disk.percent,
        ),
        environments=int(environment_count),
        version=__version__,
    )
