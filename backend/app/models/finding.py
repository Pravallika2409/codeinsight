from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class FindingRecord(Base):
    """Persisted counterpart of the in-memory `Finding` Pydantic schema
    (app/schemas/analysis.py). Column names intentionally mirror the
    schema's fields so serializing one to the other is a straight mapping.
    """

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)

    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    file: Mapped[str] = mapped_column(String(255), default="submitted_code")
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column: Mapped[int | None] = mapped_column(Integer, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    why_it_matters: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    improved_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="findings")
