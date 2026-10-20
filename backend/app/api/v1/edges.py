from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_api_key
from app.db import get_db
from app.models.graph import Edge, Node
from app.schemas.graph import EdgeCreate, EdgeOut

router = APIRouter(prefix="/edges", tags=["edges"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=list[EdgeOut])
def list_edges(
    node_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Edge]:
    query = db.query(Edge).order_by(Edge.created_at.desc())
    if node_id:
        query = query.filter((Edge.from_id == node_id) | (Edge.to_id == node_id))
    return query.limit(200).all()


@router.post("", response_model=EdgeOut, status_code=201)
def create_edge(body: EdgeCreate, db: Session = Depends(get_db)) -> Edge:
    if not db.get(Node, body.from_id) or not db.get(Node, body.to_id):
        raise HTTPException(400, "from_id and to_id must be valid nodes")
    edge = Edge(
        from_id=body.from_id,
        to_id=body.to_id,
        rel_type=body.rel_type.strip() or "related_to",
        label=body.label or "",
    )
    db.add(edge)
    db.commit()
    db.refresh(edge)
    return edge


@router.delete("/{edge_id}", status_code=204)
def delete_edge(edge_id: UUID, db: Session = Depends(get_db)) -> None:
    edge = db.get(Edge, edge_id)
    if not edge:
        raise HTTPException(404, "Edge not found")
    db.delete(edge)
    db.commit()
