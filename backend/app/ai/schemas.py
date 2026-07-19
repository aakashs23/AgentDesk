"""Request/response shapes for the AI endpoints."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ClassificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    predicted_category_id: uuid.UUID | None
    predicted_priority_id: uuid.UUID | None
    confidence: float
    confidence_tier: str
    model_version: str
    was_overridden: bool
    overridden_by: uuid.UUID | None
    corrected_category_id: uuid.UUID | None
    corrected_priority_id: uuid.UUID | None
    created_at: datetime


class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    generated_by_model: str
    draft_content: str
    confidence_score: float | None
    review_status: str
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    final_comment_id: uuid.UUID | None
    created_at: datetime


class InsightsOut(BaseModel):
    classification: ClassificationOut | None
    drafts: list[DraftOut]


class DraftReview(BaseModel):
    action: Literal["approved", "edited", "rejected"]
    content: str | None = None  # required when action == "edited"


class ClassificationCorrection(BaseModel):
    category_id: uuid.UUID | None = None
    priority_id: uuid.UUID | None = None
