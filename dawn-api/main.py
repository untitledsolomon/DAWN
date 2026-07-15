"""DAWN API — Digital AI Working Network"""
import sys
import asyncio
import logging

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from routers import (
    chat, chat_sessions, nodes, search, ingest, agent, settings as settings_router,
    ssh_hosts, osint, pentest, integrations, monitoring, books, agent_tasks,
    mcp, audit, bi,
    multimodal, data_analysis, documents, email, blockchain,
    security, performance, disaster_recovery, ai_models, dev_experience,
    community, edge_iot, agi, self_diagnosis,
    artifacts,
    decision_intelligence,
    explainer,
    slack,  # v36.0 — Slack Integration
    memories,  # v40.0 — Personal Memories API
    secrets,   # v40.0 — Encrypted Secrets Vault
    control_center,  # v37.0 — Control Center Integration
)

app = FastAPI(
    title="DAWN API",
    description="Digital AI Working Network — knowledge layer for Regent",
    version="3.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Core ────────────────────────────────────────────────────────────────────
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(chat_sessions.router, prefix="/chat", tags=["chat"])
app.include_router(nodes.router, prefix="/nodes", tags=["nodes"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
app.include_router(agent.router, prefix="/agent", tags=["agent"])
app.include_router(settings_router.router, prefix="", tags=["settings"])

# ─── v3.0 — SSH ──────────────────────────────────────────────────────────────
app.include_router(ssh_hosts.router, prefix="", tags=["ssh"])

# ─── v4.0 — MCP ──────────────────────────────────────────────────────────────
app.include_router(mcp.router, prefix="", tags=["mcp"])

# ─── v5.0 — OSINT ────────────────────────────────────────────────────────────
app.include_router(osint.router, prefix="", tags=["osint"])

# ─── v6.0 — Pentesting ───────────────────────────────────────────────────────
app.include_router(pentest.router, prefix="", tags=["pentest"])

# ─── v7.0 — Books & Learning ─────────────────────────────────────────────────
app.include_router(books.router, prefix="", tags=["books"])

# ─── v9.0 — Business Intelligence ────────────────────────────────────────────
app.include_router(bi.router, prefix="", tags=["bi"])

# ─── v10.0 — Regent Integrations ─────────────────────────────────────────────
app.include_router(integrations.router, prefix="", tags=["integrations"])

# ─── v12.0 — Multi-Modal ─────────────────────────────────────────────────────
app.include_router(multimodal.router, prefix="", tags=["multimodal"])

# ─── v13.0 — Monitoring & Alerting ───────────────────────────────────────────
app.include_router(monitoring.router, prefix="", tags=["monitoring"])

# ─── v15.0 — Audit ───────────────────────────────────────────────────────────
app.include_router(audit.router, prefix="", tags=["audit"])

# ─── v16.0 — Agent Tasks ─────────────────────────────────────────────────────
app.include_router(agent_tasks.router, prefix="", tags=["agent-tasks"])

# ─── v17.0 — Natural Language Data Analysis ──────────────────────────────────
app.include_router(data_analysis.router, prefix="", tags=["data-analysis"])

# ─── v18.0 — Document Management ─────────────────────────────────────────────
app.include_router(documents.router, prefix="", tags=["documents"])

# ─── v19.0 — Email & Communication ───────────────────────────────────────────
app.include_router(email.router, prefix="", tags=["email"])

# ─── v21.0 — Blockchain & Web3 ───────────────────────────────────────────────
app.include_router(blockchain.router, prefix="", tags=["blockchain"])

# ─── v22.0 — Security & Compliance ───────────────────────────────────────────
app.include_router(security.router, prefix="", tags=["security"])

# ─── v23.0 — Performance & Scaling ───────────────────────────────────────────
app.include_router(performance.router, prefix="", tags=["performance"])

# ─── v24.0 — Disaster Recovery ───────────────────────────────────────────────
app.include_router(disaster_recovery.router, prefix="", tags=["disaster-recovery"])

# ─── v25.0 — AI Model Improvements ───────────────────────────────────────────
app.include_router(ai_models.router, prefix="", tags=["ai-models"])

# ─── v26.0 — Developer Experience ────────────────────────────────────────────
app.include_router(dev_experience.router, prefix="", tags=["developer-experience"])

# ─── v27.0 — Community & Ecosystem ───────────────────────────────────────────
app.include_router(community.router, prefix="", tags=["community"])

# ─── v28.0 — Edge & IoT ──────────────────────────────────────────────────────
app.include_router(edge_iot.router, prefix="", tags=["edge-iot"])

# ─── v29.0 — AGI Foundations ─────────────────────────────────────────────────
app.include_router(agi.router, prefix="", tags=["agi"])

# ─── v30.0 — Self-Diagnosis & Improvement Engine ─────────────────────────────
app.include_router(self_diagnosis.router, prefix="", tags=["diagnosis"])

# ─── v20.0 — Artifacts (Visualizations, Charts, Files) ───────────────────────
app.include_router(artifacts.router, prefix="/artifacts", tags=["artifacts"])

# ─── v32.0 — Decision Intelligence ───────────────────────────────────────────
app.include_router(decision_intelligence.router, prefix="", tags=["decision-intelligence"])

# ─── v35.0 — Explainer (animated whiteboard-style HTML/SVG/JS artifacts) ─────
app.include_router(explainer.router, prefix="/explainer", tags=["explainer"])

# ─── v36.0 — Slack Integration ───────────────────────────────────────────────
app.include_router(slack.router, prefix="", tags=["slack"])

# ─── v37.0 — Control Center Integration ──────────────────────────────────────
app.include_router(control_center.router, prefix="", tags=["control-center"])

# ─── v40.0 — Personal Memories & Secrets Vault ───────────────────────────────
app.include_router(memories.router, prefix="/memories", tags=["memories"])
app.include_router(secrets.router, prefix="/secrets", tags=["secrets"])


@app.get("/health")
def health():
    from config import settings
    return {
        "status": "ok",
        "version": "3.2.0",
        "llm_mode": settings.llm_mode,
    }


# ─── Startup / Shutdown ──────────────────────────────────────────────────────

@app.on_event("startup")
async def start_background_services():
    """Start background services: pentest scheduler, ingestion queue, Slack bot,
    sub-agent registry, and dynamic agents."""
    # Pentest scheduler
    try:
        from tools.scheduler import get_scheduler
        scheduler = get_scheduler()
        await scheduler.start()
        logger.info("Pentest scheduler started")
    except Exception as e:
        logger.error(f"Failed to start pentest scheduler: {e}")

    # Ingestion queue
    try:
        from routers.ingest import ingestion_queue
        await ingestion_queue.start()
        logger.info("Ingestion queue started")
    except Exception as e:
        logger.error(f"Failed to start ingestion queue: {e}")

    # Decision workflow cache — loads ontology_workflows into memory.
    try:
        from decision_engine.registry import refresh_workflows
        await refresh_workflows()
        logger.info("Decision workflows loaded")
    except Exception as e:
        logger.error(f"Failed to load decision workflows: {e}")

    # v37.0: Load sub-agent registry
    try:
        from slack_bot.sub_agents.registry import get_sub_agent_registry
        registry = get_sub_agent_registry()
        count = len(registry.list_agents())
        logger.info(f"Sub-agent registry loaded: {count} agents")
    except Exception as e:
        logger.error(f"Failed to load sub-agent registry: {e}")

    # v37.0: Load dynamic agents from database
    try:
        from slack_bot.dynamic_agents import load_agents_from_db
        await load_agents_from_db()
    except Exception as e:
        logger.error(f"Failed to load dynamic agents: {e}")

    # v37.0: Start dynamic agent scheduler
    try:
        from slack_bot.dynamic_agents import start_dynamic_agent_scheduler
        scheduler = start_dynamic_agent_scheduler()
        if scheduler:
            logger.info("Dynamic agent scheduler started")
    except Exception as e:
        logger.error(f"Failed to start dynamic agent scheduler: {e}")

    # Slack bot — auto-start if tokens are configured
    try:
        import os
        bot_token = os.environ.get("SLACK_BOT_TOKEN")
        app_token = os.environ.get("SLACK_APP_TOKEN")
        if bot_token and app_token:
            import threading
            from slack_bot.app import start_slack_bot
            thread = threading.Thread(target=start_slack_bot, daemon=True)
            thread.start()
            logger.info("Slack bot started in background thread")
        else:
            logger.info("Slack bot not started — SLACK_BOT_TOKEN or SLACK_APP_TOKEN not set")
    except Exception as e:
        logger.error(f"Failed to start Slack bot: {e}")


@app.on_event("shutdown")
async def stop_background_services():
    """Stop background services."""
    # Pentest scheduler
    try:
        from tools.scheduler import get_scheduler
        scheduler = get_scheduler()
        await scheduler.stop()
        logger.info("Pentest scheduler stopped")
    except Exception as e:
        logger.error(f"Failed to stop pentest scheduler: {e}")

    # Ingestion queue
    try:
        from routers.ingest import ingestion_queue
        await ingestion_queue.stop()
        logger.info("Ingestion queue stopped")
    except Exception as e:
        logger.error(f"Failed to stop ingestion queue: {e}")
