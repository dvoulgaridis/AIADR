"""Task-local inputs and commit-ready results for source analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.domain.finding import Finding
from app.models.model import Model


@dataclass(frozen=True, slots=True)
class SourceInput:
    """Resolved inputs shared by source-specific analysis functions."""

    session_id: str
    source_path: Path
    source_sha256: str
    model: Model
    system_prompt: str
    image_prompt: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisResult:
    """Complete source-analysis output ready for policy mapping."""

    findings: tuple[Finding, ...]
    rejected_count: int

    def __post_init__(self) -> None:
        if self.rejected_count < 0:
            raise ValueError("rejected_count must be non-negative")


@dataclass(frozen=True, slots=True, kw_only=True)
class PdfAnalysisResult(AnalysisResult):
    """Complete visual PDF output ready for atomic review replacement."""

    page_count: int

    def __post_init__(self) -> None:
        AnalysisResult.__post_init__(self)
        if self.page_count < 1:
            raise ValueError("page_count must be at least 1")
