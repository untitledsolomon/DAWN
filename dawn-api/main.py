import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from routers import chat, nodes, search, ingest, agent

app = FastAPI(
    title="DAWN API",
    description="Digital AI Working Network — knowledge layer for Regent",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(nodes.router, prefix="/nodes", tags=["nodes"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
app.include_router(agent.router, prefix="/agent", tags=["agent"])


@app.get("/health")
def health():
    from config import settings
    return {
        "status": "ok",
        "version": "1.0.0",
        "llm_mode": settings.llm_mode,
    }


# ── __init__ files ────────────────────────────────────────────────────────────
# (created separately but noted here for clarity)
