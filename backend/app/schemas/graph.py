from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.graph import InboxStatus, NodeType


class NodeCreate(BaseModel):
    name: str
    type: NodeType = NodeType.other


class NodeUpdate(BaseModel):
    name: str | None = None
    type: NodeType | None = None


class SummaryOut(BaseModel):
    id: UUID
    node_id: UUID
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SummaryCreate(BaseModel):
    content: str


class FactOut(BaseModel):
    id: UUID
    node_id: UUID
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NodeOut(BaseModel):
    id: UUID
    type: NodeType
    name: str
    created_at: datetime
    updated_at: datetime
    summaries: list[SummaryOut] = []
    facts: list[FactOut] = []

    model_config = {"from_attributes": True}


class FactCreate(BaseModel):
    content: str


class FactUpdate(BaseModel):
    content: str


class EdgeCreate(BaseModel):
    from_id: UUID
    to_id: UUID
    rel_type: str = "related_to"
    label: str = ""


class EdgeOut(BaseModel):
    id: UUID
    from_id: UUID
    to_id: UUID
    rel_type: str
    label: str
    created_at: datetime

    model_config = {"from_attributes": True}


class InboxCreate(BaseModel):
    raw_text: str = Field(min_length=1)


class InboxUpdate(BaseModel):
    raw_text: str | None = None
    proposal: dict[str, Any] | None = None


class InboxOut(BaseModel):
    id: UUID
    raw_text: str
    proposal: dict[str, Any] | None
    status: InboxStatus
    error: str | None
    created_at: datetime
    approved_at: datetime | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=30)


class SourceOut(BaseModel):
    node_id: UUID
    node_name: str
    fact_id: UUID
    content: str
    score: float | None = None
    kind: str = "fact"


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
