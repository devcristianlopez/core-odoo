"""Public response/request models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class HealthResponse(BaseModel):
    status: str
    odoo: bool
    odoo_version: str | None = None
    version: str


class CreateResponse(BaseModel):
    id: int


class UpdateResponse(BaseModel):
    updated: bool = True
    id: int


class DeleteResponse(BaseModel):
    deleted: bool = True
    id: int


Record = dict[str, Any]
