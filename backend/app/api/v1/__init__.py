from fastapi import APIRouter

from app.api.v1 import edges, inbox, nodes, query, speech

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(nodes.router)
api_router.include_router(edges.router)
api_router.include_router(inbox.router)
api_router.include_router(query.router)
api_router.include_router(speech.router)
