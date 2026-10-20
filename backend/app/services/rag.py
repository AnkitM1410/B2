from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.graph import Edge, Fact, Node, Summary
from app.schemas.graph import QueryResponse, SourceOut
from app.services import llm


async def query_graph(db: Session, question: str, top_k: int = 8) -> QueryResponse:
    try:
        qvec = await llm.embed_one(question)
    except Exception as exc:  # noqa: BLE001
        return QueryResponse(
            answer=f"Could not embed question (check embedding API keys): {exc}",
            sources=[],
        )

    candidates: list[tuple[str, UUID, str, UUID, str, float | None]] = []

    fact_dist = Fact.embedding.cosine_distance(qvec)
    fact_rows = db.execute(
        select(Fact, fact_dist.label("distance"))
        .options(joinedload(Fact.node))
        .where(Fact.embedding.is_not(None))
        .order_by(fact_dist)
        .limit(top_k)
    ).unique().all()
    for fact, distance in fact_rows:
        score = None if distance is None else float(1.0 / (1.0 + float(distance)))
        candidates.append(("fact", fact.id, fact.content, fact.node_id, fact.node.name, score))

    sum_dist = Summary.embedding.cosine_distance(qvec)
    sum_rows = db.execute(
        select(Summary, sum_dist.label("distance"))
        .options(joinedload(Summary.node))
        .where(Summary.embedding.is_not(None))
        .order_by(sum_dist)
        .limit(top_k)
    ).unique().all()
    for summary, distance in sum_rows:
        score = None if distance is None else float(1.0 / (1.0 + float(distance)))
        candidates.append(
            ("summary", summary.id, summary.content, summary.node_id, summary.node.name, score)
        )

    candidates.sort(key=lambda c: -(c[5] or 0))
    candidates = candidates[:top_k]

    sources: list[SourceOut] = []
    context_bits: list[str] = []
    node_ids: set[UUID] = set()

    for kind, entry_id, content, node_id, node_name, score in candidates:
        node_ids.add(node_id)
        sources.append(
            SourceOut(
                node_id=node_id,
                node_name=node_name,
                fact_id=entry_id,
                content=content,
                score=score,
                kind=kind,
            )
        )
        label = "summary" if kind == "summary" else "fact"
        context_bits.append(f"- [{node_name} / {label}] {content}")

    neighbor_lines: list[str] = []
    if node_ids:
        edges = (
            db.query(Edge)
            .filter((Edge.from_id.in_(node_ids)) | (Edge.to_id.in_(node_ids)))
            .limit(40)
            .all()
        )
        related_ids = set()
        for e in edges:
            related_ids.add(e.from_id)
            related_ids.add(e.to_id)
        related_ids -= node_ids
        name_by_id = {
            n.id: n.name for n in db.query(Node).filter(Node.id.in_(node_ids | related_ids)).all()
        }
        for e in edges:
            neighbor_lines.append(
                f"- {name_by_id.get(e.from_id, '?')} --{e.rel_type}--> {name_by_id.get(e.to_id, '?')}"
                + (f" ({e.label})" if e.label else "")
            )
        if related_ids:
            for n in db.query(Node).filter(Node.id.in_(related_ids)).all():
                recent = (
                    db.query(Summary)
                    .filter(Summary.node_id == n.id)
                    .order_by(Summary.created_at.desc())
                    .limit(2)
                    .all()
                )
                for s in recent:
                    neighbor_lines.append(f"- Neighbor {n.name}: {s.content}")

    if not context_bits:
        return QueryResponse(
            answer="I don't have enough stored notes to answer that yet. Add via Inbox or node edit.",
            sources=[],
        )

    context = "Notes:\n" + "\n".join(context_bits)
    if neighbor_lines:
        context += "\n\nLinks:\n" + "\n".join(neighbor_lines[:30])

    messages = [
        {
            "role": "system",
            "content": (
                "You answer questions using only the provided B2 memory-graph context. "
                "Be concise. If unsure, say so. Mention people/things by name."
            ),
        },
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]
    try:
        answer = await llm.chat(messages)
    except Exception as exc:  # noqa: BLE001
        answer = f"LLM error (check LLM_API_KEY / model): {exc}"

    return QueryResponse(answer=answer, sources=sources)
