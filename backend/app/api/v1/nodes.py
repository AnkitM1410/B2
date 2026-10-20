from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.api.deps import require_api_key
from app.db import get_db
from app.models.graph import Fact, Node
from app.schemas.graph import FactCreate, FactOut, FactUpdate, NodeCreate, NodeOut, NodeUpdate
from app.services.embeddings import embed_fact_safe

router = APIRouter(prefix="/nodes", tags=["nodes"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=list[NodeOut])
def list_nodes(
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[Node]:
    query = db.query(Node).options(joinedload(Node.facts)).order_by(Node.updated_at.desc())
    if q:
        query = query.filter(Node.name.ilike(f"%{q}%"))
    return query.limit(limit).all()


@router.post("", response_model=NodeOut, status_code=201)
def create_node(body: NodeCreate, db: Session = Depends(get_db)) -> Node:
    node = Node(name=body.name.strip(), type=body.type, summary=body.summary or "")
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


@router.get("/{node_id}", response_model=NodeOut)
def get_node(node_id: UUID, db: Session = Depends(get_db)) -> Node:
    node = db.query(Node).options(joinedload(Node.facts)).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(404, "Node not found")
    return node


@router.patch("/{node_id}", response_model=NodeOut)
def update_node(node_id: UUID, body: NodeUpdate, db: Session = Depends(get_db)) -> Node:
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    if body.name is not None:
        node.name = body.name.strip()
    if body.type is not None:
        node.type = body.type
    if body.summary is not None:
        node.summary = body.summary
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


@router.delete("/{node_id}", status_code=204)
def delete_node(node_id: UUID, db: Session = Depends(get_db)) -> None:
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    db.delete(node)
    db.commit()


@router.post("/{node_id}/facts", response_model=FactOut, status_code=201)
async def add_fact(node_id: UUID, body: FactCreate, db: Session = Depends(get_db)) -> Fact:
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    fact = Fact(node_id=node.id, content=body.content.strip())
    db.add(fact)
    db.commit()
    db.refresh(fact)
    await embed_fact_safe(db, fact)
    db.refresh(fact)
    return fact


@router.patch("/{node_id}/facts/{fact_id}", response_model=FactOut)
async def update_fact(
    node_id: UUID, fact_id: UUID, body: FactUpdate, db: Session = Depends(get_db)
) -> Fact:
    fact = db.query(Fact).filter(Fact.id == fact_id, Fact.node_id == node_id).first()
    if not fact:
        raise HTTPException(404, "Fact not found")
    fact.content = body.content.strip()
    db.add(fact)
    db.commit()
    db.refresh(fact)
    await embed_fact_safe(db, fact)
    db.refresh(fact)
    return fact


@router.delete("/{node_id}/facts/{fact_id}", status_code=204)
def delete_fact(node_id: UUID, fact_id: UUID, db: Session = Depends(get_db)) -> None:
    fact = db.query(Fact).filter(Fact.id == fact_id, Fact.node_id == node_id).first()
    if not fact:
        raise HTTPException(404, "Fact not found")
    db.delete(fact)
    db.commit()
