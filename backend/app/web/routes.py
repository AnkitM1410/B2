import json
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models.graph import Edge, Fact, InboxItem, InboxStatus, Node, NodeType, Summary
from app.services import inbox as inbox_service
from app.services.embeddings import embed_fact_safe
from app.services.rag import query_graph

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/templates")


def _render(request: Request, name: str, context: dict | None = None) -> HTMLResponse:
    ctx = {"request": request}
    if context:
        ctx.update(context)
    return templates.TemplateResponse(name, ctx)


@router.get("/", response_class=HTMLResponse)
def home() -> RedirectResponse:
    return RedirectResponse("/inbox", status_code=302)


@router.get("/inbox", response_class=HTMLResponse)
def inbox_page(
    request: Request,
    db: Session = Depends(get_db),
    status: str = Query(default="pending"),
) -> HTMLResponse:
    try:
        st = InboxStatus(status)
    except ValueError:
        st = InboxStatus.pending
    items = (
        db.query(InboxItem)
        .filter(InboxItem.status == st)
        .order_by(InboxItem.created_at.desc())
        .limit(50)
        .all()
    )
    return _render(request, "inbox.html", {"items": items, "status": st.value})


@router.post("/inbox", response_class=HTMLResponse)
async def inbox_capture(
    request: Request,
    raw_text: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    await inbox_service.create_inbox_item(db, raw_text)
    return RedirectResponse("/inbox", status_code=303)


@router.get("/inbox/{item_id}", response_class=HTMLResponse)
def inbox_detail(request: Request, item_id: UUID, db: Session = Depends(get_db)) -> HTMLResponse:
    item = db.get(InboxItem, item_id)
    if not item:
        raise HTTPException(404, "Not found")
    proposal_json = json.dumps(item.proposal or {}, indent=2, ensure_ascii=False)
    return _render(request, "inbox_detail.html", {"item": item, "proposal_json": proposal_json})


@router.post("/inbox/{item_id}/save", response_class=HTMLResponse)
def inbox_save(
    item_id: UUID,
    raw_text: str = Form(...),
    proposal_json: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    item = db.get(InboxItem, item_id)
    if not item or item.status != InboxStatus.pending:
        raise HTTPException(400, "Cannot edit")
    item.raw_text = raw_text
    try:
        item.proposal = json.loads(proposal_json)
        item.error = None
    except json.JSONDecodeError as exc:
        item.error = f"Invalid JSON: {exc}"
    db.add(item)
    db.commit()
    return RedirectResponse(f"/inbox/{item_id}", status_code=303)


@router.post("/inbox/{item_id}/repropose", response_class=HTMLResponse)
async def inbox_repropose(item_id: UUID, db: Session = Depends(get_db)) -> RedirectResponse:
    item = db.get(InboxItem, item_id)
    if not item:
        raise HTTPException(404)
    await inbox_service.repropose(db, item)
    return RedirectResponse(f"/inbox/{item_id}", status_code=303)


@router.post("/inbox/{item_id}/approve", response_class=HTMLResponse)
async def inbox_approve(item_id: UUID, db: Session = Depends(get_db)) -> RedirectResponse:
    item = db.get(InboxItem, item_id)
    if not item:
        raise HTTPException(404)
    await inbox_service.apply_proposal(db, item)
    return RedirectResponse("/inbox", status_code=303)


@router.post("/inbox/{item_id}/reject", response_class=HTMLResponse)
def inbox_reject(item_id: UUID, db: Session = Depends(get_db)) -> RedirectResponse:
    item = db.get(InboxItem, item_id)
    if not item:
        raise HTTPException(404)
    inbox_service.reject_item(db, item)
    return RedirectResponse("/inbox", status_code=303)


@router.get("/nodes", response_class=HTMLResponse)
def nodes_page(
    request: Request,
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    query = db.query(Node).options(joinedload(Node.summaries)).order_by(Node.updated_at.desc())
    if q:
        query = query.filter(Node.name.ilike(f"%{q}%"))
    nodes = query.limit(100).all()
    return _render(request, "nodes.html", {"nodes": nodes, "q": q or ""})


@router.post("/nodes", response_class=HTMLResponse)
def nodes_create(
    name: str = Form(...),
    type: str = Form(default="other"),
    summary: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        ntype = NodeType(type)
    except ValueError:
        ntype = NodeType.other
    node = Node(name=name.strip(), type=ntype)
    db.add(node)
    db.flush()  # get id before adding summary
    if summary.strip():
        s = Summary(node_id=node.id, content=summary.strip())
        db.add(s)
    db.commit()
    db.refresh(node)
    return RedirectResponse(f"/nodes/{node.id}", status_code=303)


@router.get("/nodes/{node_id}", response_class=HTMLResponse)
def node_detail(request: Request, node_id: UUID, db: Session = Depends(get_db)) -> HTMLResponse:
    node = (
        db.query(Node)
        .options(joinedload(Node.facts), joinedload(Node.summaries))
        .filter(Node.id == node_id)
        .first()
    )
    if not node:
        raise HTTPException(404)
    edges = (
        db.query(Edge)
        .filter((Edge.from_id == node_id) | (Edge.to_id == node_id))
        .all()
    )
    all_nodes = {n.id: n for n in db.query(Node).all()}
    return _render(
        request,
        "node_detail.html",
        {"node": node, "edges": edges, "all_nodes": all_nodes, "types": list(NodeType)},
    )


@router.post("/nodes/{node_id}", response_class=HTMLResponse)
def node_update(
    node_id: UUID,
    name: str = Form(...),
    type: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(404)
    node.name = name.strip()
    try:
        node.type = NodeType(type)
    except ValueError:
        pass
    db.add(node)
    db.commit()
    return RedirectResponse(f"/nodes/{node_id}", status_code=303)


@router.post("/nodes/{node_id}/summaries", response_class=HTMLResponse)
def node_add_summary(
    node_id: UUID,
    content: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(404)
    s = Summary(node_id=node.id, content=content.strip())
    db.add(s)
    db.commit()
    return RedirectResponse(f"/nodes/{node_id}", status_code=303)


@router.post("/nodes/{node_id}/summaries/{summary_id}/delete", response_class=HTMLResponse)
def node_delete_summary(
    node_id: UUID,
    summary_id: UUID,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    s = db.query(Summary).filter(Summary.id == summary_id, Summary.node_id == node_id).first()
    if s:
        db.delete(s)
        db.commit()
    return RedirectResponse(f"/nodes/{node_id}", status_code=303)


@router.post("/nodes/{node_id}/facts", response_class=HTMLResponse)
async def node_add_fact(
    node_id: UUID,
    content: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(404)
    fact = Fact(node_id=node.id, content=content.strip())
    db.add(fact)
    db.commit()
    db.refresh(fact)
    await embed_fact_safe(db, fact)
    return RedirectResponse(f"/nodes/{node_id}", status_code=303)


@router.post("/nodes/{node_id}/facts/{fact_id}/delete", response_class=HTMLResponse)
def node_delete_fact(node_id: UUID, fact_id: UUID, db: Session = Depends(get_db)) -> RedirectResponse:
    fact = db.query(Fact).filter(Fact.id == fact_id, Fact.node_id == node_id).first()
    if fact:
        db.delete(fact)
        db.commit()
    return RedirectResponse(f"/nodes/{node_id}", status_code=303)


@router.post("/nodes/{node_id}/edges", response_class=HTMLResponse)
def node_add_edge(
    node_id: UUID,
    to_id: UUID = Form(...),
    rel_type: str = Form(default="related_to"),
    label: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if not db.get(Node, node_id) or not db.get(Node, to_id):
        raise HTTPException(400, "Invalid nodes")
    edge = Edge(from_id=node_id, to_id=to_id, rel_type=rel_type.strip() or "related_to", label=label)
    db.add(edge)
    db.commit()
    return RedirectResponse(f"/nodes/{node_id}", status_code=303)


@router.post("/edges/{edge_id}/delete", response_class=HTMLResponse)
def edge_delete(edge_id: UUID, node_id: UUID = Form(...), db: Session = Depends(get_db)) -> RedirectResponse:
    edge = db.get(Edge, edge_id)
    if edge:
        db.delete(edge)
        db.commit()
    return RedirectResponse(f"/nodes/{node_id}", status_code=303)


@router.get("/query", response_class=HTMLResponse)
def query_page(request: Request) -> HTMLResponse:
    return _render(request, "query.html", {"answer": None, "sources": [], "question": ""})


@router.post("/query", response_class=HTMLResponse)
async def query_submit(
    request: Request,
    question: str = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    result = await query_graph(db, question.strip())
    return _render(
        request,
        "query.html",
        {"answer": result.answer, "sources": result.sources, "question": question},
    )
