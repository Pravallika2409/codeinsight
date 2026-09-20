from __future__ import annotations

import datetime as dt
from typing import List

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.database.session import Base


class ProjectFile(Base):
    """A named file within a project. Each analysis run belongs to one of these.

    Named `ProjectFile` (not `File`) to avoid clashing with Python's builtin.
    """

    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped["Project"] = relationship(back_populates="files")
    analysis_runs: Mapped[List["AnalysisRun"]] = relationship(back_populates="file", cascade="all, delete-orphan")
