"""
v30.0 — Self-Diagnosis & Improvement Engine
Analyzes DAWN's own architecture, database state, codebase, and deployment
environment to produce a concrete, prioritized improvement roadmap.

This is the missing piece that lets DAWN answer "how to improve DAWN using ML"
with something useful — because it knows itself.
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from config import settings as app_settings
import db.client as db

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != app_settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ──── Schemas ────────────────────────────────────────────────────────────────

class DiagnosisRequest(BaseModel):
    focus: Optional[str] = None  # 'ml', 'performance', 'knowledge', 'all'
    include_code_analysis: bool = False


# ──── Helpers ────────────────────────────────────────────────────────────────

def _count_table(table: str, filters: Optional[dict] = None) -> int:
    """Count rows in a table with optional filters."""
    try:
        supabase = db.get_db()
        q = supabase.table(table).select("id", count="exact")
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        res = q.execute()
        return res.count if hasattr(res, 'count') and res.count is not None else len(res.data or [])
    except Exception as e:
        logger.warning(f"[diagnosis] count {table} failed: {e}")
        return -1


def _get_recent(table: str, column: str = "created_at", days: int = 7) -> int:
    """Count rows created in the last N days."""
    try:
        supabase = db.get_db()
        since = datetime.now(timezone.utc).isoformat()
        # We approximate by fetching recent and counting
        res = supabase.table(table).select("id").gte(column, since).execute()
        return len(res.data or [])
    except Exception:
        return -1


def _check_endpoint_stub(path: str, stub_indicator: str = "time.sleep") -> bool:
    """Check if a file contains a stub implementation."""
    try:
        full_path = os.path.join(os.path.dirname(__file__), "..", path)
        if not os.path.exists(full_path):
            return True  # missing = stub
        with open(full_path) as f:
            content = f.read()
        return stub_indicator in content
    except Exception:
        return True


def _get_file_size(path: str) -> Optional[int]:
    """Get file size in bytes."""
    try:
        full_path = os.path.join(os.path.dirname(__file__), "..", path)
        return os.path.getsize(full_path)
    except Exception:
        return None


def _check_import_available(module_name: str) -> bool:
    """Check if a Python module is importable."""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


# ──── Diagnosis Endpoint ─────────────────────────────────────────────────────

@router.get("/diagnosis", tags=["diagnosis"])
async def get_diagnosis(
    focus: str = "all",
    include_code_analysis: bool = False,
    _=None,
):
    """
    Run a full self-diagnosis of DAWN's architecture, data, and capabilities.
    Returns a structured report with concrete improvement recommendations.
    """
    try:
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "3.0.0",
            "llm_mode": app_settings.llm_mode,
            "focus": focus,
        }

        # ── 1. Database Health ──────────────────────────────────────────
        db_health = _diagnose_database()
        report["database"] = db_health

        # ── 2. Knowledge Graph Health ───────────────────────────────────
        kg_health = _diagnose_knowledge_graph()
        report["knowledge_graph"] = kg_health

        # ── 3. ML/AI Capabilities ───────────────────────────────────────
        if focus in ("all", "ml"):
            report["ml_capabilities"] = _diagnose_ml_capabilities()

        # ── 4. Performance & Infrastructure ─────────────────────────────
        if focus in ("all", "performance"):
            report["infrastructure"] = _diagnose_infrastructure()

        # ── 5. Codebase Health ──────────────────────────────────────────
        if include_code_analysis or focus == "code":
            report["codebase"] = _diagnose_codebase()

        # ── 6. Improvement Roadmap ──────────────────────────────────────
        report["improvements"] = _generate_improvements(db_health, kg_health, focus)

        # ── 7. Self-Knowledge Summary ───────────────────────────────────
        report["self_knowledge"] = _summarize_self_knowledge()

        return report

    except Exception as e:
        logger.error(f"[diagnosis] failed: {e}")
        raise HTTPException(status_code=500, detail=f"Diagnosis failed: {str(e)}")


def _diagnose_database() -> dict:
    """Check database connectivity and table health."""
    result = {
        "connected": False,
        "tables": {},
        "issues": [],
    }

    try:
        supabase = db.get_db()
        # Ping
        ping = supabase.table("nodes").select("id").limit(1).execute()
        result["connected"] = True

        # Count key tables
        tables_to_check = [
            "nodes", "edges", "tags", "node_tags",
            "chat_sessions", "chat_messages",
            "ingestion_log", "memory_sessions",
            "error_patterns", "knowledge_gaps",
            "fine_tune_jobs", "model_configs",
            "agent_logs", "meta_cognition_logs",
            "curiosity_explorations", "agi_goals",
            "self_improvement_sessions",
        ]

        for table in tables_to_check:
            count = _count_table(table)
            result["tables"][table] = {
                "row_count": count,
                "has_data": count > 0 if count >= 0 else "unknown",
            }

        # Check for issues
        if result["tables"].get("chat_messages", {}).get("row_count", 0) == 0:
            result["issues"].append("chat_messages table is empty — no conversation data to learn from")

        if result["tables"].get("error_patterns", {}).get("row_count", 0) == 0:
            result["issues"].append("error_patterns table is empty — no error learning data")

        if result["tables"].get("fine_tune_jobs", {}).get("row_count", 0) == 0:
            result["issues"].append("fine_tune_jobs table is empty — no fine-tuning has been attempted")

        if result["tables"].get("model_configs", {}).get("row_count", 0) == 0:
            result["issues"].append("model_configs table is empty — no alternative models configured")

    except Exception as e:
        result["issues"].append(f"Database connection failed: {str(e)}")

    return result


def _diagnose_knowledge_graph() -> dict:
    """Analyze the knowledge graph structure and health."""
    result = {
        "total_nodes": 0,
        "total_edges": 0,
        "by_type": {},
        "by_status": {},
        "by_source": {},
        "orphan_nodes": 0,  # nodes with no edges
        "stale_nodes": 0,
        "draft_nodes": 0,
        "issues": [],
    }

    try:
        supabase = db.get_db()

        # Total counts
        result["total_nodes"] = _count_table("nodes")
        result["total_edges"] = _count_table("edges")

        # Count by type
        for ntype in ["concept", "entity", "process", "fact", "memory", "document", "table"]:
            count = _count_table("nodes", {"type": ntype})
            if count > 0:
                result["by_type"][ntype] = count

        # Count by status
        for status in ["active", "draft", "stale", "archived"]:
            count = _count_table("nodes", {"status": status})
            if count > 0:
                result["by_status"][status] = count

        # Count by source
        for source in ["manual", "repo", "conversation", "document", "web"]:
            count = _count_table("nodes", {"source": source})
            if count > 0:
                result["by_source"][source] = count

        # Stale and draft counts
        result["stale_nodes"] = _count_table("nodes", {"status": "stale"})
        result["draft_nodes"] = _count_table("nodes", {"status": "draft"})

        # Issues
        if result["total_nodes"] == 0:
            result["issues"].append("Knowledge graph is empty — no nodes exist")

        if result["total_edges"] == 0 and result["total_nodes"] > 0:
            result["issues"].append("No edges in the graph — nodes are isolated, traversal will return nothing")

        if result["draft_nodes"] > 0:
            result["issues"].append(
                f"{result['draft_nodes']} draft nodes need review before they become active"
            )

        if result["stale_nodes"] > 0:
            result["issues"].append(
                f"{result['stale_nodes']} stale nodes may contain outdated information"
            )

        # Check for orphan nodes (nodes with no edges)
        if result["total_nodes"] > 0:
            try:
                # Get all node IDs
                nodes_res = supabase.table("nodes").select("id").eq("status", "active").limit(1000).execute()
                all_ids = [n["id"] for n in (nodes_res.data or [])]
                if all_ids:
                    # Check which have edges
                    edge_res = supabase.table("edges").select("from_node").limit(5000).execute()
                    connected_ids = set()
                    for e in (edge_res.data or []):
                        connected_ids.add(e["from_node"])
                    orphans = [nid for nid in all_ids if nid not in connected_ids]
                    result["orphan_nodes"] = len(orphans)
                    if result["orphan_nodes"] > 0:
                        result["issues"].append(
                            f"{result['orphan_nodes']} active nodes have no edges — they won't be found by graph traversal"
                        )
            except Exception:
                pass

    except Exception as e:
        result["issues"].append(f"Knowledge graph analysis failed: {str(e)}")

    return result


def _diagnose_ml_capabilities() -> dict:
    """Analyze ML/AI capabilities and identify gaps."""
    result = {
        "embedding_model": "all-MiniLM-L6-v2",
        "embedding_dim": 384,
        "llm_mode": app_settings.llm_mode,
        "llm_model": app_settings.deepseek_model if app_settings.llm_mode == "deepseek" else (app_settings.local_model_path or "unknown"),
        "capabilities": {},
        "stubs": [],
        "missing_dependencies": [],
        "issues": [],
    }

    # Check what's actually available
    result["capabilities"]["embeddings"] = _check_import_available("sentence_transformers")
    result["capabilities"]["fine_tuning"] = _check_import_available("transformers") and _check_import_available("torch")
    result["capabilities"]["local_llm"] = _check_import_available("llama_cpp")
    result["capabilities"]["sklearn"] = _check_import_available("sklearn")
    result["capabilities"]["scipy"] = _check_import_available("scipy")
    result["capabilities"]["pandas"] = _check_import_available("pandas")

    # Check for stubs in the codebase
    stub_checks = [
        ("fine_tuning", "routers/ai_models.py", "time.sleep(2)"),
        ("rag_optimization", "routers/ai_models.py", "suggestions.append"),
    ]
    for name, path, indicator in stub_checks:
        if _check_endpoint_stub(path, indicator):
            result["stubs"].append(name)

    # Check missing dependencies
    if not result["capabilities"]["fine_tuning"]:
        result["missing_dependencies"].append("transformers + torch (needed for local fine-tuning)")

    # Issues
    if result["stubs"]:
        result["issues"].append(
            f"Stub implementations found: {', '.join(result['stubs'])} — these endpoints don't actually do anything"
        )

    if result["missing_dependencies"]:
        result["issues"].append(
            f"Missing dependencies: {', '.join(result['missing_dependencies'])}"
        )

    # Check if fine_tune_jobs has any completed jobs
    ft_count = _count_table("fine_tune_jobs", {"status": "completed"})
    if ft_count == 0:
        result["issues"].append("No completed fine-tuning jobs — the fine-tuning pipeline has never been used")

    # Check if model_configs has alternatives
    mc_count = _count_table("model_configs")
    if mc_count == 0:
        result["issues"].append("No alternative model configs — DAWN only uses the default LLM")

    return result


def _diagnose_infrastructure() -> dict:
    """Analyze deployment environment and performance constraints."""
    result = {
        "platform": "unknown",
        "ram_gb": "unknown",
        "cpu_cores": "unknown",
        "has_gpu": False,
        "disk_space_gb": "unknown",
        "containerized": False,
        "issues": [],
    }

    # Check if running in Docker
    result["containerized"] = os.path.exists("/.dockerenv")

    # Platform detection
    try:
        import platform
        result["platform"] = platform.platform()
    except Exception:
        pass

    # RAM
    try:
        import psutil
        mem = psutil.virtual_memory()
        result["ram_gb"] = round(mem.total / (1024**3), 1)
        result["ram_available_gb"] = round(mem.available / (1024**3), 1)
        if mem.total < 8 * 1024**3:
            result["issues"].append(
                f"Only {result['ram_gb']}GB RAM — cannot run 7B+ models locally, consider quantized 3B models or API-based LLM"
            )
    except ImportError:
        result["issues"].append("psutil not available — cannot measure memory")

    # CPU
    try:
        result["cpu_cores"] = os.cpu_count() or "unknown"
        if isinstance(result["cpu_cores"], int) and result["cpu_cores"] < 4:
            result["issues"].append(
                f"Only {result['cpu_cores']} CPU cores — embedding generation and local inference will be slow"
            )
    except Exception:
        pass

    # GPU
    try:
        import torch
        result["has_gpu"] = torch.cuda.is_available()
        if result["has_gpu"]:
            result["gpu_name"] = torch.cuda.get_device_name(0)
            result["gpu_memory_gb"] = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 1)
    except ImportError:
        pass

    # Disk
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        result["disk_total_gb"] = round(total / (1024**3), 1)
        result["disk_free_gb"] = round(free / (1024**3), 1)
        if free < 10 * 1024**3:
            result["issues"].append(
                f"Only {result['disk_free_gb']}GB free disk — may run out of space for model downloads or ingestion"
            )
    except Exception:
        pass

    # Check if local model path is configured and exists
    if app_settings.llm_mode == "local":
        if app_settings.local_model_path:
            if os.path.exists(app_settings.local_model_path):
                size_gb = os.path.getsize(app_settings.local_model_path) / (1024**3)
                result["local_model_size_gb"] = round(size_gb, 1)
            else:
                result["issues"].append(
                    f"Local model path configured but file not found: {app_settings.local_model_path}"
                )
        else:
            result["issues"].append("LLM_MODE=local but LOCAL_MODEL_PATH is not set")

    return result


def _diagnose_codebase() -> dict:
    """Analyze the codebase structure and health."""
    result = {
        "total_python_files": 0,
        "total_lines": 0,
        "routers": [],
        "tools": [],
        "llm_modules": [],
        "issues": [],
    }

    base = os.path.join(os.path.dirname(__file__), "..")

    # Count Python files
    py_files = []
    for root, dirs, files in os.walk(base):
        # Skip __pycache__, .git, venv
        if "__pycache__" in root or ".git" in root or "venv" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))

    result["total_python_files"] = len(py_files)

    # Count lines
    total_lines = 0
    for pf in py_files:
        try:
            with open(pf) as f:
                total_lines += len(f.readlines())
        except Exception:
            pass
    result["total_lines"] = total_lines

    # List routers
    routers_dir = os.path.join(base, "routers")
    if os.path.exists(routers_dir):
        for f in sorted(os.listdir(routers_dir)):
            if f.endswith(".py") and f != "__init__.py":
                fpath = os.path.join(routers_dir, f)
                size = os.path.getsize(fpath)
                result["routers"].append({
                    "name": f.replace(".py", ""),
                    "size_bytes": size,
                    "size_kb": round(size / 1024, 1),
                })

    # List tools
    tools_dir = os.path.join(base, "tools")
    if os.path.exists(tools_dir):
        for f in sorted(os.listdir(tools_dir)):
            if f.endswith(".py") and f != "__init__.py":
                result["tools"].append(f.replace(".py", ""))

    # List llm modules
    llm_dir = os.path.join(base, "llm")
    if os.path.exists(llm_dir):
        for f in sorted(os.listdir(llm_dir)):
            if f.endswith(".py") and f != "__init__.py":
                result["llm_modules"].append(f.replace(".py", ""))

    return result


def _generate_improvements(db_health: dict, kg_health: dict, focus: str) -> list[dict]:
    """Generate a prioritized list of concrete improvements."""
    improvements = []

    # ── Data Collection Improvements ──────────────────────────────────
    if focus in ("all", "ml"):
        improvements.append({
            "priority": "P0 - Critical",
            "category": "data_collection",
            "title": "Collect preference data for RLHF",
            "description": (
                "DAWN has no mechanism to collect user feedback on response quality. "
                "Without preference pairs (good vs bad responses), RLHF or reward model "
                "training is impossible. Add a thumbs-up/thumbs-down UI element and store "
                "preferences in a new 'response_feedback' table."
            ),
            "effort": "Medium (2-3 days)",
            "impact": "Enables all downstream RLHF/alignment work",
            "depends_on": [],
        })

        improvements.append({
            "priority": "P0 - Critical",
            "category": "data_collection",
            "title": "Implement actual fine-tuning (not a stub)",
            "description": (
                "The /ai/fine-tune endpoint currently calls time.sleep(2) and returns fake metrics. "
                "Replace with actual LoRA fine-tuning using transformers + PEFT, or integrate "
                "with OpenAI's fine-tuning API for DeepSeek models."
            ),
            "effort": "Medium (3-5 days)",
            "impact": "Enables domain-specific model improvements",
            "depends_on": ["Install transformers + torch + peft"],
        })

    # ── Knowledge Graph Improvements ───────────────────────────────────
    if focus in ("all", "knowledge", "ml"):
        if kg_health.get("orphan_nodes", 0) > 0:
            improvements.append({
                "priority": "P1 - High",
                "category": "knowledge_graph",
                "title": f"Connect {kg_health['orphan_nodes']} orphan nodes to the graph",
                "description": (
                    f"{kg_health['orphan_nodes']} active nodes have no edges. "
                    "Run an automated linking pass: for each orphan, fuzzy-search existing "
                    "nodes and create 'related_to' edges to the top 3 matches. This is the "
                    "same approach already used in _link_node_to_related() in chat.py."
                ),
                "effort": "Low (1 day)",
                "impact": "Immediately improves graph traversal recall",
                "depends_on": [],
            })

        if kg_health.get("draft_nodes", 0) > 0:
            improvements.append({
                "priority": "P1 - High",
                "category": "knowledge_graph",
                "title": f"Review {kg_health['draft_nodes']} draft memory nodes",
                "description": (
                    f"{kg_health['draft_nodes']} memory nodes are in 'draft' status and won't "
                    "be returned by queries. Either auto-promote high-confidence drafts (>0.8) "
                    "to active, or build a review UI."
                ),
                "effort": "Low (0.5 day)",
                "impact": "Unlocks trapped knowledge",
                "depends_on": [],
            })

    # ── ML-Specific Improvements ───────────────────────────────────────
    if focus in ("all", "ml"):
        improvements.append({
            "priority": "P1 - High",
            "category": "ml",
            "title": "Add response quality scoring with a learned reward model",
            "description": (
                "Train a small BERT-based classifier (or use the LLM itself) to score "
                "response quality on dimensions: accuracy, helpfulness, conciseness. "
                "Use this to (a) flag low-quality responses for review, (b) build a "
                "training dataset of high-quality examples."
            ),
            "effort": "Medium (3-4 days)",
            "impact": "Automated quality monitoring + training data generation",
            "depends_on": ["Collect preference data for RLHF"],
        })

        improvements.append({
            "priority": "P1 - High",
            "category": "ml",
            "title": "Implement active learning for knowledge gaps",
            "description": (
                "DAWN has a knowledge_gaps table but nothing actively fills it. "
                "Add a post-response step: if the LLM's confidence is low or it says "
                "'I don't know', log the topic as a knowledge gap. Periodically suggest "
                "documents to ingest that fill these gaps."
            ),
            "effort": "Medium (2-3 days)",
            "impact": "Systematic knowledge expansion",
            "depends_on": [],
        })

        improvements.append({
            "priority": "P2 - Medium",
            "category": "ml",
            "title": "Fine-tune a small local model with LoRA",
            "description": (
                f"Given {app_settings.llm_mode} mode and the current infrastructure, "
                "fine-tune a quantized 3B model (e.g., Phi-3-mini-4k-instruct-q4) using "
                "LoRA on DAWN-specific data (Regent products, Uganda context, trading systems). "
                "This would run locally without API costs."
            ),
            "effort": "Medium (3-5 days)",
            "impact": "Faster, cheaper, offline-capable DAWN",
            "depends_on": ["Implement actual fine-tuning (not a stub)", "Collect preference data for RLHF"],
        })

        improvements.append({
            "priority": "P2 - Medium",
            "category": "ml",
            "title": "Conversation clustering for pattern discovery",
            "description": (
                "Use sentence embeddings on chat messages + HDBSCAN clustering to group "
                "similar conversations. This reveals: (a) frequently asked topics that lack "
                "knowledge graph coverage, (b) recurring user intents, (c) response quality "
                "patterns per cluster."
            ),
            "effort": "Medium (2-3 days)",
            "impact": "Data-driven prioritization of knowledge gaps",
            "depends_on": [],
        })

        improvements.append({
            "priority": "P2 - Medium",
            "category": "ml",
            "title": "Automated prompt optimization via bandit testing",
            "description": (
                "Run A/B tests on system prompt variations (e.g., different context formatting, "
                "different instruction phrasings). Use a multi-armed bandit to select the best "
                "performer based on response quality scores. Store winning prompts per query type."
            ),
            "effort": "Medium (3-4 days)",
            "impact": "Continuously improving response quality without manual tuning",
            "depends_on": ["Add response quality scoring with a learned reward model"],
        })

    # ── Infrastructure Improvements ────────────────────────────────────
    if focus in ("all", "performance"):
        improvements.append({
            "priority": "P2 - Medium",
            "category": "infrastructure",
            "title": "Add Redis caching for frequent queries",
            "description": (
                "Many queries hit the same knowledge graph nodes repeatedly. Add Redis "
                "caching with TTL for: (a) fuzzy search results, (b) traversal results, "
                "(c) embedding results. Redis is already in requirements.txt (commented out)."
            ),
            "effort": "Low (1 day)",
            "impact": "Reduces latency for common queries by 50-80%",
            "depends_on": [],
        })

    # ── Self-Knowledge Improvements ────────────────────────────────────
    improvements.append({
        "priority": "P1 - High",
        "category": "self_knowledge",
        "title": "Ingest DAWN's own codebase into its knowledge graph",
        "description": (
            "DAWN cannot currently answer questions about its own architecture because "
            "it hasn't ingested its own source code. Run the repo ingestion on DAWN's "
            "own repository so it knows what endpoints exist, what's a stub vs real, "
            "and how its components connect."
        ),
        "effort": "Low (0.5 day)",
        "impact": "Enables DAWN to answer 'how do I...' questions about itself",
        "depends_on": [],
    })

    improvements.append({
        "priority": "P1 - High",
        "category": "self_knowledge",
        "title": "Add a /diagnosis endpoint (this!) to DAWN's chat context",
        "description": (
            "The /diagnosis endpoint exists but DAWN doesn't know about it. Add it to "
            "the system prompt or make it a tool so DAWN can self-diagnose on demand "
            "when asked 'how to improve DAWN'."
        ),
        "effort": "Low (0.5 day)",
        "impact": "Completes the self-awareness loop",
        "depends_on": [],
    })

    # Sort by priority
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    improvements.sort(key=lambda x: priority_order.get(x["priority"][:2], 99))

    return improvements


def _summarize_self_knowledge() -> dict:
    """Summarize what DAWN knows about itself."""
    return {
        "knows_its_own_codebase": False,  # Not ingested yet
        "knows_its_own_endpoints": False,  # Not in system prompt
        "knows_its_own_database_schema": False,  # Not ingested
        "knows_its_own_deployment": False,  # Not ingested
        "has_self_diagnosis_endpoint": True,  # This file!
        "recommendation": (
            "Ingest DAWN's own repository and add the diagnosis endpoint to the system prompt. "
            "This will close the self-awareness gap completely."
        ),
    }


# ──── Quick Health Check ─────────────────────────────────────────────────────

@router.get("/diagnosis/health", tags=["diagnosis"])
async def quick_health(_=None):
    """Quick health check with key metrics."""
    try:
        supabase = db.get_db()
        ping = supabase.table("nodes").select("id").limit(1).execute()
        db_ok = True
    except Exception:
        db_ok = False

    node_count = _count_table("nodes") if db_ok else -1
    chat_count = _count_table("chat_messages") if db_ok else -1

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "llm_mode": app_settings.llm_mode,
        "nodes": node_count,
        "chat_messages": chat_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
