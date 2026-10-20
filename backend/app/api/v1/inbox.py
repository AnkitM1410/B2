from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_api_key
from app.db import get_db
from app.models.graph import InboxItem, InboxStatus
from app.schemas.graph import InboxCreate, InboxOut, InboxUpdate
from app.services import inbox as inbox_service

router = APIRouter(prefix="/inbox", tags=["inbox"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=list[InboxOut])
def list_inbox(
    status: InboxStatus | None = Query(default=InboxStatus.pending),
    db: Session = Depends(get_db),
) -> list[InboxItem]:
    query = db.query(InboxItem).order_by(InboxItem.created_at.desc())
    if status:
        query = query.filter(InboxItem.status == status)
    return query.limit(100).all()


@router.post("", response_model=InboxOut, status_code=201)
async def create_inbox(body: InboxCreate, db: Session = Depends(get_db)) -> InboxItem:
    return await inbox_service.create_inbox_item(db, body.raw_text)


@router.get("/{item_id}", response_model=InboxOut)
def get_inbox(item_id: UUID, db: Session = Depends(get_db)) -> InboxItem:
    item = db.get(InboxItem, item_id)
    if not item:
        raise HTTPException(404, "Inbox item not found")
    return item


@router.patch("/{item_id}", response_model=InboxOut)
def update_inbox(item_id: UUID, body: InboxUpdate, db: Session = Depends(get_db)) -> InboxItem:
    item = db.get(InboxItem, item_id)
    if not item:
        raise HTTPException(404, "Inbox item not found")
    if item.status != InboxStatus.pending:
        raise HTTPException(400, "Only pending items can be edited")
    if body.raw_text is not None:
        item.raw_text = body.raw_text
    if body.proposal is not None:
        item.proposal = body.proposal
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/repropose", response_model=InboxOut)
async def repropose(item_id: UUID, db: Session = Depends(get_db)) -> InboxItem:
    item = db.get(InboxItem, item_id)
    if not item:
        raise HTTPException(404, "Inbox item not found")
    if item.status != InboxStatus.pending:
        raise HTTPException(400, "Only pending items can be re-proposed")
    return await inbox_service.repropose(db, item)


@router.post("/{item_id}/approve", response_model=InboxOut)
async def approve(item_id: UUID, db: Session = Depends(get_db)) -> InboxItem:
    item = db.get(InboxItem, item_id)
    if not item:
        raise HTTPException(404, "Inbox item not found")
    try:
        return await inbox_service.apply_proposal(db, item)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{item_id}/reject", response_model=InboxOut)
def reject(item_id: UUID, db: Session = Depends(get_db)) -> InboxItem:
    item = db.get(InboxItem, item_id)
    if not item:
        raise HTTPException(404, "Inbox item not found")
    try:
        return inbox_service.reject_item(db, item)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put("/{item_id}/proposal-json", response_model=InboxOut)
def update_proposal_json(item_id: UUID, body: dict, db: Session = Depends(get_db)) -> InboxItem:
    """Replace proposal from a JSON object (used by HTML form textarea)."""
    item = db.get(InboxItem, item_id)
    if not item:
        raise HTTPException(404, "Inbox item not found")
    if item.status != InboxStatus.pending:
        raise HTTPException(400, "Only pending items can be edited")
    item.proposal = body
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
