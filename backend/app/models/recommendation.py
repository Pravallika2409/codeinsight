from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.database.session import Base


class Recommendation(Base):
    """An AI-generated recommendation attached to an analysis run.

    Populated by app/services/history_service.py whenever an analysis was
    both persisted (project_id given) and included a successful AI review
    (include_ai_review=True and the AI call succeeded) -- see Phase 4 in
    the README. Table existed since Phase 3 with a stable schema; this is
    the first phase anything reads or writes it.
    """

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="recommendations")
