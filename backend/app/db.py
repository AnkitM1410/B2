from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create extension, tables, and lightweight schema patches for existing DBs."""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE inbox_items ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ")
        )
        # Migrate legacy single summary text into dated summary entries once
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                  IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'nodes' AND column_name = 'summary'
                  ) THEN
                    INSERT INTO summaries (id, node_id, content, created_at)
                    SELECT gen_random_uuid(), id, summary, COALESCE(updated_at, created_at, NOW())
                    FROM nodes
                    WHERE summary IS NOT NULL AND TRIM(summary) <> ''
                      AND NOT EXISTS (
                        SELECT 1 FROM summaries s WHERE s.node_id = nodes.id
                      );
                  END IF;
                END $$;
                """
            )
        )
