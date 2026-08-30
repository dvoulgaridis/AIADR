"""Pydantic models for review findings and media targets."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.sources.docx_text import DocxStoryKind
from app.sources.kinds import SourceKind


class PrivacyCategory(StrEnum):
    NOT_PERSONAL_DATA = "not_personal_data"
    PERSONAL_DATA = "personal_data"
    SPECIAL_CATEGORY = "special_category"
    UNKNOWN = "unknown"


class SpecialCategoryType(StrEnum):
    NONE = "none"
    RACIAL_OR_ETHNIC_ORIGIN = "racial_or_ethnic_origin"
    POLITICAL_OPINION = "political_opinion"
    RELIGIOUS_OR_PHILOSOPHICAL_BELIEF = "religious_or_philosophical_belief"
    TRADE_UNION_MEMBERSHIP = "trade_union_membership"
    GENETIC_DATA = "genetic_data"
    BIOMETRIC_IDENTIFICATION = "biometric_identification"
    HEALTH_DATA = "health_data"
    SEX_LIFE_OR_SEXUAL_ORIENTATION = "sex_life_or_sexual_orientation"


class DataSubjectContext(StrEnum):
    ADULT = "adult"
    MINOR = "minor"
    UNKNOWN = "unknown"


class PrivacyRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingOrigin(StrEnum):
    MODEL = "model"
    REVIEWER = "reviewer"
    SYSTEM = "system"


class ReviewDecision(StrEnum):
    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"
    PRESERVED = "preserved"


class ImageSurfaceType(StrEnum):
    """Coordinate surface addressed by an image target."""

    FILE = "file"
    PDF_PAGE = "pdf_page"
    DOCX_PICTURE = "docx_picture"


class DocumentLocatorFormat(StrEnum):
    TEXT = "text"
    DOCX = "docx"


class TargetRegion(BaseModel):
    """Normalized top-left-origin target region for visual findings."""

    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    width: float = Field(..., gt=0.0, le=1.0)
    height: float = Field(..., gt=0.0, le=1.0)
    rotation_degrees: float = 0.0

    @field_validator("rotation_degrees")
    @classmethod
    def normalize_rotation(cls, value: float) -> float:
        return ((value + 180.0) % 360.0) - 180.0

    @model_validator(mode="after")
    def region_must_fit_unit_space(self) -> TargetRegion:
        if self.x + self.width > 1.0 or self.y + self.height > 1.0:
            raise ValueError("target region must fit inside normalized [0, 1] media bounds")
        return self

    model_config = {"frozen": True}


class AudioRange(BaseModel):
    """Inclusive-start, exclusive-end audio range."""

    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., gt=0.0)

    @model_validator(mode="after")
    def end_must_follow_start(self) -> AudioRange:
        if self.end_time <= self.start_time:
            raise ValueError("audio end_time must be greater than start_time")
        return self

    model_config = {"frozen": True}


class FileImageSurface(BaseModel):
    type: Literal[ImageSurfaceType.FILE] = ImageSurfaceType.FILE

    model_config = {"extra": "forbid", "frozen": True}


class PdfPageSurface(BaseModel):
    type: Literal[ImageSurfaceType.PDF_PAGE] = ImageSurfaceType.PDF_PAGE
    page: int = Field(ge=1)

    model_config = {"extra": "forbid", "frozen": True}


class DocxPictureSurface(BaseModel):
    type: Literal[ImageSurfaceType.DOCX_PICTURE] = ImageSurfaceType.DOCX_PICTURE
    occurrence_id: str = Field(pattern=r"^pic_[0-9a-f]{64}$")

    model_config = {"extra": "forbid", "frozen": True}


ImageSurface: TypeAlias = Annotated[
    FileImageSurface | PdfPageSurface | DocxPictureSurface,
    Field(discriminator="type"),
]


class ImageTarget(BaseModel):
    kind: Literal[SourceKind.IMAGE] = SourceKind.IMAGE
    surface: ImageSurface
    region: TargetRegion

    model_config = {"extra": "forbid", "frozen": True}


class PlainTextLocator(BaseModel):
    format: Literal[DocumentLocatorFormat.TEXT] = DocumentLocatorFormat.TEXT
    line_id: str = Field(min_length=1)
    exact_text: str = Field(min_length=1)

    model_config = {"extra": "forbid", "frozen": True}


class DocxTextLocator(BaseModel):
    format: Literal[DocumentLocatorFormat.DOCX] = DocumentLocatorFormat.DOCX
    page: int = Field(ge=1)
    line_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    story_kind: DocxStoryKind
    part_uri: str = Field(min_length=1)
    block_id: str = Field(pattern=r"^b_[0-9a-f]{64}$")
    exact_text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> DocxTextLocator:
        if self.end <= self.start:
            raise ValueError("DOCX target end must be greater than start")
        if self.end - self.start != len(self.exact_text):
            raise ValueError("DOCX target range must equal the exact text length")
        return self

    model_config = {"extra": "forbid", "frozen": True}


DocumentLocator: TypeAlias = Annotated[
    PlainTextLocator | DocxTextLocator,
    Field(discriminator="format"),
]


class DocumentTarget(BaseModel):
    kind: Literal[SourceKind.DOCUMENT] = SourceKind.DOCUMENT
    locator: DocumentLocator

    model_config = {"extra": "forbid", "frozen": True}


class AudioTarget(BaseModel):
    kind: Literal[SourceKind.AUDIO] = SourceKind.AUDIO
    range: AudioRange

    model_config = {"extra": "forbid", "frozen": True}


FindingTarget: TypeAlias = Annotated[
    ImageTarget | DocumentTarget | AudioTarget,
    Field(discriminator="kind"),
]


class Finding(BaseModel):
    """A single model, reviewer, or system finding."""

    id: str
    target: FindingTarget

    detected_entity_type: str | None = None
    reviewed_entity_type: str | None = None
    privacy_category: PrivacyCategory = PrivacyCategory.UNKNOWN
    special_category_type: SpecialCategoryType = SpecialCategoryType.NONE
    data_subject_context: DataSubjectContext = DataSubjectContext.UNKNOWN

    label: str
    detection_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    privacy_risk: PrivacyRisk = PrivacyRisk.MEDIUM

    description: str | None = None
    reason: str | None = None

    origin: FindingOrigin = FindingOrigin.MODEL
    created_by: str | None = None
    review_decision: ReviewDecision = ReviewDecision.NEEDS_REVIEW
    edited: bool = False
    reviewer_note: str | None = None

    @property
    def kind(self) -> SourceKind:
        return self.target.kind

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_entity_type(self) -> str:
        """Return the reviewer correction, detected value, or policy fallback key."""
        return self.reviewed_entity_type or self.detected_entity_type or "unknown"

    model_config = {"extra": "forbid", "frozen": True}
