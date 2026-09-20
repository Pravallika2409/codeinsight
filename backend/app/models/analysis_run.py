from __future__ import annotations

import datetime as dt
from typing import List

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.database.session import Base


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)  # snapshot of what was analyzed

    score_total: Mapped[int] = mapped_column(Integer, nullable=False)
    score_base: Mapped[int] = mapped_column(Integer, default=100)
    bug_penalty: Mapped[int] = mapped_column(Integer, default=0)
    security_penalty: Mapped[int] = mapped_column(Integer, default=0)
    complexity_penalty: Mapped[int] = mapped_column(Integer, default=0)
    maintainability_penalty: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    time_complexity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    space_complexity: Mapped[str | None] = mapped_column(String(50), nullable=True)

    critical_count: Mapped[int] = mapped_column(Integer, default=0)
    high_count: Mapped[int] = mapped_column(Integer, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, default=0)
    low_count: Mapped[int] = mapped_column(Integer, default=0)
    info_count: Mapped[int] = mapped_column(Integer, default=0)

    # AI review (Phase 4) -- all nullable: an anonymous/no-AI run leaves
    # these unset rather than storing a fabricated placeholder.
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_overall_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_improved_code: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    file: Mapped["ProjectFile"] = relationship(back_populates="analysis_runs")
    findings: Mapped[List["FindingRecord"]] = relationship(back_populates="analysis_run", cascade="all, delete-orphan")
    recommendations: Mapped[List["Recommendation"]] = relationship(back_populates="analysis_run", cascade="all, delete-orphan")
