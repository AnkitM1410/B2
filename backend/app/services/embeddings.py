from sqlalchemy.orm import Session

from app.models.graph import Fact, Summary
from app.services import llm


async def embed_fact(db: Session, fact: Fact) -> None:
    fact.embedding = await llm.embed_one(fact.content)
    db.add(fact)
    db.commit()


async def embed_summary(db: Session, summary: Summary) -> None:
    summary.embedding = await llm.embed_one(summary.content)
    db.add(summary)
    db.commit()


async def embed_fact_safe(db: Session, fact: Fact) -> str | None:
    try:
        await embed_fact(db, fact)
        return None
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return str(exc)


async def embed_summary_safe(db: Session, summary: Summary) -> str | None:
    try:
        await embed_summary(db, summary)
        return None
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return str(exc)
