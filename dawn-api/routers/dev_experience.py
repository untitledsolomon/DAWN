"""
v26.0 — Developer Experience
Local dev environment, seed data, E2E tests, API tests, load testing, docs
"""
import json
import logging
import os
import subprocess
from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from config import settings as app_settings
import db.client as db

logger = logging.getLogger(__name__)
router = APIRouter()

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != app_settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ─── Schemas ──────────────────────────────────────────────────────────────

class TestRunRequest(BaseModel):
    test_type: str = "api"  # 'api', 'e2e', 'integration', 'unit'
    endpoint: Optional[str] = None
    concurrent: int = 1

class SeedDataRequest(BaseModel):
    tables: list[str] = ["all"]
    count: int = 10

# ─── API Documentation ────────────────────────────────────────────────────

@router.get("/dev/docs/summary", tags=["developer-experience"])
async def get_api_docs_summary(_: None = Depends(verify_key)):
    """Get a summary of all API endpoints."""
    try:
        # Get all registered routes from the FastAPI app
        from main import app
        
        endpoints = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method in ("GET", "POST", "PUT", "DELETE"):
                        endpoints.append({
                            "method": method,
                            "path": route.path,
                            "name": route.name if hasattr(route, "name") else "",
                        })
        
        # Group by prefix
        grouped = {}
        for ep in endpoints:
            prefix = ep["path"].split("/")[1] if ep["path"] != "/" else "root"
            if prefix not in grouped:
                grouped[prefix] = []
            grouped[prefix].append(ep)
        
        return {
            "total_endpoints": len(endpoints),
            "groups": {k: len(v) for k, v in sorted(grouped.items())},
            "endpoints_by_method": {
                "GET": sum(1 for e in endpoints if e["method"] == "GET"),
                "POST": sum(1 for e in endpoints if e["method"] == "POST"),
                "PUT": sum(1 for e in endpoints if e["method"] == "PUT"),
                "DELETE": sum(1 for e in endpoints if e["method"] == "DELETE"),
            },
        }
    except Exception as e:
        logger.error(f"[dev] docs summary failed: {e}")
        return {"error": str(e)}


@router.get("/dev/docs/openapi", tags=["developer-experience"])
async def get_openapi_spec(_: None = Depends(verify_key)):
    """Get the OpenAPI specification."""
    try:
        from main import app
        return app.openapi()
    except Exception as e:
        logger.error(f"[dev] openapi failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get OpenAPI spec: {str(e)}")


# ─── Seed Data Generation ─────────────────────────────────────────────────

@router.post("/dev/seed", tags=["developer-experience"])
async def generate_seed_data(
    req: SeedDataRequest,
    _: None = Depends(verify_key),
):
    """Generate seed data for development/testing."""
    try:
        supabase = db.get_db()
        results = {}
        
        seed_data = {
            "nodes": [
                {"title": "DAWN Architecture Overview", "type": "documentation", "body": "DAWN is built with FastAPI, Next.js, and Supabase.", "status": "published"},
                {"title": "SSH Configuration Guide", "type": "guide", "body": "How to configure SSH hosts for remote access.", "status": "published"},
                {"title": "OSINT Best Practices", "type": "guide", "body": "Guidelines for OSINT operations.", "status": "draft"},
                {"title": "Solomon's Preferences", "type": "preference", "body": "Prefers concise, actionable responses.", "status": "published"},
                {"title": "Regent CRM Overview", "type": "business", "body": "Customer relationship management system.", "status": "published"},
            ],
            "tags": [
                {"name": "documentation", "description": "Technical documentation"},
                {"name": "guide", "description": "How-to guides"},
                {"name": "security", "description": "Security-related content"},
                {"name": "business", "description": "Business operations"},
                {"name": "development", "description": "Software development"},
            ],
            "ssh_hosts": [
                {"label": "Paperclip VPS", "hostname": "paperclip.regent.ug", "port": 22, "username": "root", "auth_method": "key"},
                {"label": "Staging Server", "hostname": "staging.regent.ug", "port": 22, "username": "deploy", "auth_method": "key"},
            ],
            "books": [
                {"title": "The Pragmatic Programmer", "author": "Andy Hunt", "category": "computer_science", "ingested": False},
                {"title": "Designing Data-Intensive Applications", "author": "Martin Kleppmann", "category": "computer_science", "ingested": False},
                {"title": "Security Engineering", "author": "Ross Anderson", "category": "security", "ingested": False},
            ],
        }
        
        tables_to_seed = req.tables if req.tables != ["all"] else list(seed_data.keys())
        
        for table in tables_to_seed:
            if table in seed_data:
                try:
                    # Clear existing data first
                    try:
                        supabase.table(table).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
                    except Exception:
                        pass
                    
                    # Insert seed data
                    res = supabase.table(table).insert(seed_data[table]).execute()
                    results[table] = len(res.data or [])
                except Exception as e:
                    results[table] = f"Error: {str(e)}"
        
        return {
            "status": "seeded",
            "results": results,
            "message": "Seed data generated. You may need to run the SQL migration first if tables don't exist.",
        }
    except Exception as e:
        logger.error(f"[dev] seed failed: {e}")
        raise HTTPException(status_code=500, detail=f"Seed failed: {str(e)}")


# ─── Test Runner ──────────────────────────────────────────────────────────

@router.post("/dev/tests/run", tags=["developer-experience"])
async def run_tests(
    req: TestRunRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_key),
):
    """Run tests and return results."""
    try:
        supabase = db.get_db()
        
        test_run = supabase.table("test_runs").insert({
            "test_type": req.test_type,
            "endpoint": req.endpoint,
            "status": "running",
        }).execute()
        
        run_id = test_run.data[0]["id"] if test_run.data else None
        
        if run_id:
            background_tasks.add_task(_run_tests, run_id, req)
        
        return {"run_id": run_id, "status": "running", "test_type": req.test_type}
    
    except Exception as e:
        logger.error(f"[dev] test run failed: {e}")
        raise HTTPException(status_code=500, detail=f"Test run failed: {str(e)}")


def _run_tests(run_id: str, req: TestRunRequest):
    """Run tests in background."""
    try:
        supabase = db.get_db()
        results = []
        
        if req.test_type == "api":
            # Test key API endpoints
            import httpx
            import time
            
            base_url = "http://localhost:8000"
            headers = {"X-API-Key": app_settings.dawn_api_key}
            
            endpoints_to_test = [
                ("GET", "/health", None),
                ("GET", "/settings", None),
                ("GET", "/nodes/", None),
                ("GET", "/chat/sessions", None),
            ]
            
            if req.endpoint:
                endpoints_to_test = [("GET", req.endpoint, None)]
            
            for method, path, body in endpoints_to_test:
                start = time.time()
                try:
                    if method == "GET":
                        resp = httpx.get(f"{base_url}{path}", headers=headers, timeout=5)
                    elif method == "POST":
                        resp = httpx.post(f"{base_url}{path}", headers=headers, json=body or {}, timeout=5)
                    
                    duration = (time.time() - start) * 1000
                    results.append({
                        "method": method,
                        "path": path,
                        "status": resp.status_code,
                        "duration_ms": round(duration, 2),
                        "passed": resp.status_code < 500,
                    })
                except Exception as e:
                    results.append({
                        "method": method,
                        "path": path,
                        "status": 0,
                        "duration_ms": 0,
                        "passed": False,
                        "error": str(e),
                    })
        
        passed = sum(1 for r in results if r["passed"])
        failed = sum(1 for r in results if not r["passed"])
        
        supabase.table("test_runs").update({
            "status": "completed",
            "completed_at": "now()",
            "total_tests": len(results),
            "passed": passed,
            "failed": failed,
            "results": json.dumps(results),
        }).eq("id", run_id).execute()
    
    except Exception as e:
        logger.error(f"[dev] background test run failed: {e}")
        try:
            supabase.table("test_runs").update({
                "status": "failed",
                "error_message": str(e),
            }).eq("id", run_id).execute()
        except Exception:
            pass


@router.get("/dev/tests/runs", tags=["developer-experience"])
async def list_test_runs(limit: int = 20, _: None = Depends(verify_key)):
    """List recent test runs."""
    try:
        supabase = db.get_db()
        res = supabase.table("test_runs").select("*").order("created_at", desc=True).limit(limit).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[dev] list test runs failed: {e}")
        return []


@router.get("/dev/tests/runs/{run_id}", tags=["developer-experience"])
async def get_test_run(run_id: str, _: None = Depends(verify_key)):
    """Get a specific test run with results."""
    try:
        supabase = db.get_db()
        res = supabase.table("test_runs").select("*").eq("id", run_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Test run not found")
        
        result = res.data[0]
        if result.get("results") and isinstance(result["results"], str):
            result["results"] = json.loads(result["results"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[dev] get test run failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get test run: {str(e)}")


# ─── Environment Info ─────────────────────────────────────────────────────

@router.get("/dev/environment", tags=["developer-experience"])
async def get_environment_info(_: None = Depends(verify_key)):
    """Get information about the current environment."""
    try:
        import platform
        import sys
        
        # Check installed packages
        installed_packages = []
        try:
            import pkg_resources
            installed_packages = [f"{d.key}=={d.version}" for d in pkg_resources.working_set]
        except Exception:
            pass
        
        return {
            "python_version": sys.version,
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "hostname": platform.node(),
            "environment": "production" if os.environ.get("DAWN_ENV") == "production" else "development",
            "api_version": "3.0.0",
            "installed_packages_count": len(installed_packages),
            "env_vars": {
                "SUPABASE_URL": "✅" if os.environ.get("SUPABASE_URL") else "❌",
                "SUPABASE_SERVICE_KEY": "✅" if os.environ.get("SUPABASE_SERVICE_KEY") else "❌",
                "DEEPSEEK_API_KEY": "✅" if os.environ.get("DEEPSEEK_API_KEY") else "❌",
                "SHODAN_API_KEY": "✅" if os.environ.get("SHODAN_API_KEY") else "❌",
                "DAWN_API_KEY": "✅" if os.environ.get("DAWN_API_KEY") else "❌",
            },
        }
    except Exception as e:
        logger.error(f"[dev] environment info failed: {e}")
        return {"error": str(e)}


# ─── Code Quality ─────────────────────────────────────────────────────────

@router.post("/dev/lint", tags=["developer-experience"])
async def run_linter(
    path: str = ".",
    _: None = Depends(verify_key),
):
    """Run linter on the codebase."""
    try:
        result = subprocess.run(
            ["ruff", "check", path, "--format", "json"],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0:
            return {"status": "clean", "message": "No linting issues found"}
        
        try:
            issues = json.loads(result.stdout)
            return {
                "status": "issues_found",
                "count": len(issues),
                "issues": issues[:50],  # Limit to 50
                "summary": {
                    "error": sum(1 for i in issues if i.get("kind") == "error"),
                    "warning": sum(1 for i in issues if i.get("kind") == "warning"),
                    "info": sum(1 for i in issues if i.get("kind") == "info"),
                },
            }
        except json.JSONDecodeError:
            return {
                "status": "issues_found",
                "raw_output": result.stdout[:2000],
                "stderr": result.stderr[:500],
            }
    except FileNotFoundError:
        return {"status": "not_available", "message": "ruff not installed. Run: pip install ruff"}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "message": "Linting timed out"}
    except Exception as e:
        logger.error(f"[dev] lint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Lint failed: {str(e)}")


# ─── Docker Compose Generator ─────────────────────────────────────────────

@router.get("/dev/docker-compose", tags=["developer-experience"])
async def generate_docker_compose(_: None = Depends(verify_key)):
    """Generate a docker-compose.yml for local development."""
    compose = """version: '3.8'

services:
  api:
    build:
      context: ./dawn-api
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./dawn-api:/app
      - ./sandbox:/sandbox
      - ./installed_skills:/installed_skills
    depends_on:
      - redis
    restart: unless-stopped

  ui:
    build:
      context: ./dawn-ui
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_DAWN_API_URL=http://localhost:8000
      - NEXT_PUBLIC_DAWN_API_KEY=dev-key
    volumes:
      - ./dawn-ui:/app
    depends_on:
      - api
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

  # Optional: Local LLM
  # ollama:
  #   image: ollama/ollama:latest
  #   ports:
  #     - "11434:11434"
  #   volumes:
  #     - ollama_data:/root/.ollama
  #   deploy:
  #     resources:
  #       reservations:
  #         devices:
  #           - driver: nvidia
  #             count: 1
  #             capabilities: [gpu]

volumes:
  redis_data:
  # ollama_data:
"""
    return {"docker_compose": compose, "filename": "docker-compose.yml"}
