import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.graph import Edge, Fact, InboxItem, InboxStatus, Node, NodeType, Summary
from app.services import llm
from app.services.embeddings import embed_fact_safe, embed_summary_safe


PROPOSE_SYSTEM = """You extract structured knowledge-graph updates from a user's note.
Return ONLY valid JSON with this shape:
{
  "nodes": [
    {"action": "create"|"update", "name": "...", "type": "person"|"thing"|"place"|"other", "temp_id": "n1"}
  ],
  "summaries": [
    {"node_temp_id": "n1", "node_name": "...", "content": "..."}
  ],
  "facts": [
    {"node_temp_id": "n1", "node_name": "...", "content": "..."}
  ],
  "edges": [
    {"from_temp_id": "n1", "to_temp_id": "n2", "from_name": "...", "to_name": "...", "rel_type": "...", "label": "..."}
  ],
  "notes": "optional short note for the reviewer"
}
Rules:
- Prefer matching existing node names from the provided catalog when referring to known people/things.
- Use temp_id only for nodes you create in this proposal; reference them from summaries/facts/edges.
- Summaries are short dated notes about a person/thing (one idea per entry). Never dump everything into one blob.
- Facts should be atomic, short statements (attributes, preferences, specifics).
- Do not invent strong claims; stick close to the note.
"""


def _node_catalog(db: Session, limit: int = 200) -> list[dict[str, Any]]:
    nodes = db.query(Node).order_by(Node.updated_at.desc()).limit(limit).all()
    catalog = []
    for n in nodes:
        recent = (
            db.query(Summary)
            .filter(Summary.node_id == n.id)
            .order_by(Summary.created_at.desc())
            .limit(3)
            .all()
        )
        catalog.append(
            {
                "id": str(n.id),
                "name": n.name,
                "type": n.type.value,
                "recent_summaries": [s.content for s in recent],
            }
        )
    return catalog


async def propose_from_text(db: Session, raw_text: str) -> dict[str, Any]:
    catalog = _node_catalog(db)
    messages = [
        {"role": "system", "content": PROPOSE_SYSTEM},
        {
            "role": "user",
            "content": (
                "Existing nodes (catalog):\n"
                + json.dumps(catalog, ensure_ascii=False)
                + "\n\nUser note:\n"
                + raw_text
            ),
        },
    ]
    return await llm.chat_json(messages)


async def create_inbox_item(db: Session, raw_text: str, *, run_propose: bool = True) -> InboxItem:
    item = InboxItem(raw_text=raw_text.strip(), status=InboxStatus.pending)
    db.add(item)
    db.commit()
    db.refresh(item)

    if run_propose:
        try:
            item.proposal = await propose_from_text(db, item.raw_text)
            item.error = None
        except Exception as exc:  # noqa: BLE001
            item.proposal = {"nodes": [], "summaries": [], "facts": [], "edges": [], "notes": ""}
            item.error = f"Proposal failed: {exc}"
        db.add(item)
        db.commit()
        db.refresh(item)
    return item


async def repropose(db: Session, item: InboxItem) -> InboxItem:
    try:
        item.proposal = await propose_from_text(db, item.raw_text)
        item.error = None
    except Exception as exc:  # noqa: BLE001
        item.error = f"Proposal failed: {exc}"
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _resolve_node_type(value: str | None) -> NodeType:
    try:
        return NodeType(value or "other")
    except ValueError:
        return NodeType.other


async def apply_proposal(db: Session, item: InboxItem) -> InboxItem:
    if item.status != InboxStatus.pending:
        raise ValueError("Only pending inbox items can be approved")
    proposal = item.proposal or {}
    temp_map: dict[str, uuid.UUID] = {}

    for node_spec in proposal.get("nodes") or []:
        name = (node_spec.get("name") or "").strip()
        if not name:
            continue
        action = (node_spec.get("action") or "create").lower()
        existing = db.query(Node).filter(Node.name.ilike(name)).first()
        if action == "update" or existing:
            node = existing or Node(name=name, type=_resolve_node_type(node_spec.get("type")))
            if node_spec.get("type"):
                node.type = _resolve_node_type(node_spec.get("type"))
            # Legacy proposals may still send a single "summary" string — turn into an entry
            legacy = (node_spec.get("summary") or "").strip()
            db.add(node)
            db.flush()
            if legacy:
                summary = Summary(node_id=node.id, content=legacy)
                db.add(summary)
                db.flush()
                await embed_summary_safe(db, summary)
        else:
            node = Node(name=name, type=_resolve_node_type(node_spec.get("type")))
            db.add(node)
            db.flush()
            legacy = (node_spec.get("summary") or "").strip()
            if legacy:
                summary = Summary(node_id=node.id, content=legacy)
                db.add(summary)
                db.flush()
                await embed_summary_safe(db, summary)
        temp_id = node_spec.get("temp_id")
        if temp_id:
            temp_map[str(temp_id)] = node.id

    def find_node(temp_id: str | None, name: str | None) -> Node | None:
        if temp_id and str(temp_id) in temp_map:
            return db.get(Node, temp_map[str(temp_id)])
        if name:
            return db.query(Node).filter(Node.name.ilike(name.strip())).first()
        return None

    for summary_spec in proposal.get("summaries") or []:
        content = (summary_spec.get("content") or "").strip()
        if not content:
            continue
        node = find_node(summary_spec.get("node_temp_id"), summary_spec.get("node_name"))
        if not node:
            nname = (summary_spec.get("node_name") or "").strip() or "Unknown"
            node = Node(name=nname, type=NodeType.other)
            db.add(node)
            db.flush()
        summary = Summary(node_id=node.id, content=content)
        db.add(summary)
        db.flush()
        await embed_summary_safe(db, summary)

    for fact_spec in proposal.get("facts") or []:
        content = (fact_spec.get("content") or "").strip()
        if not content:
            continue
        node = find_node(fact_spec.get("node_temp_id"), fact_spec.get("node_name"))
        if not node:
            nname = (fact_spec.get("node_name") or "").strip() or "Unknown"
            node = Node(name=nname, type=NodeType.other)
            db.add(node)
            db.flush()
        fact = Fact(node_id=node.id, content=content)
        db.add(fact)
        db.flush()
        await embed_fact_safe(db, fact)

    for edge_spec in proposal.get("edges") or []:
        from_node = find_node(edge_spec.get("from_temp_id"), edge_spec.get("from_name"))
        to_node = find_node(edge_spec.get("to_temp_id"), edge_spec.get("to_name"))
        if not from_node or not to_node:
            continue
        edge = Edge(
            from_id=from_node.id,
            to_id=to_node.id,
            rel_type=(edge_spec.get("rel_type") or "related_to").strip() or "related_to",
            label=(edge_spec.get("label") or "").strip(),
        )
        db.add(edge)

    item.status = InboxStatus.approved
    item.approved_at = datetime.now(timezone.utc)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def reject_item(db: Session, item: InboxItem) -> InboxItem:
    if item.status != InboxStatus.pending:
        raise ValueError("Only pending inbox items can be rejected")
    item.status = InboxStatus.rejected
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
