from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: dt.datetime
    file_count: int = 0

    model_config = {"from_attributes": True}
