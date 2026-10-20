from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_api_key
from app.db import get_db
from app.schemas.graph import QueryRequest, QueryResponse
from app.services.rag import query_graph

router = APIRouter(prefix="/query", tags=["query"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=QueryResponse)
async def query(body: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    return await query_graph(db, body.question, top_k=body.top_k)
