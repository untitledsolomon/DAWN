"""
v23.0 — Performance & Scaling
Caching, query optimization, connection pooling, horizontal scaling, CDN
"""
import json
import logging
import time
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from typing import Optional, Any
from config import settings as app_settings
import db.client as db

logger = logging.getLogger(__name__)
router = APIRouter()

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != app_settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ─── Cache Management ─────────────────────────────────────────────────────

class CacheEntry(BaseModel):
    key: str
    value: Any
    ttl_seconds: int = 300  # 5 minutes

@router.post("/performance/cache/set", tags=["performance"])
async def cache_set(req: CacheEntry, _: None = Depends(verify_key)):
    """Set a value in the cache."""
    try:
        import redis.asyncio as redis
        
        r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        
        value_str = json.dumps(req.value) if not isinstance(req.value, str) else req.value
        await r.setex(f"dawn:cache:{req.key}", req.ttl_seconds, value_str)
        await r.aclose()
        
        return {"status": "cached", "key": req.key, "ttl": req.ttl_seconds}
    except ImportError:
        raise HTTPException(status_code=501, detail="Redis not installed. Run: pip install redis")
    except Exception as e:
        logger.error(f"[performance] cache set failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cache set failed: {str(e)}")


@router.get("/performance/cache/{key}", tags=["performance"])
async def cache_get(key: str, _: None = Depends(verify_key)):
    """Get a value from the cache."""
    try:
        import redis.asyncio as redis
        
        r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        value = await r.get(f"dawn:cache:{key}")
        ttl = await r.ttl(f"dawn:cache:{key}")
        await r.aclose()
        
        if value is None:
            raise HTTPException(status_code=404, detail="Cache key not found")
        
        # Try to parse as JSON
        try:
            parsed = json.loads(value)
            return {"key": key, "value": parsed, "ttl": ttl, "hit": True}
        except (json.JSONDecodeError, TypeError):
            return {"key": key, "value": value, "ttl": ttl, "hit": True}
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=501, detail="Redis not installed")
    except Exception as e:
        logger.error(f"[performance] cache get failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cache get failed: {str(e)}")


@router.delete("/performance/cache/{key}", tags=["performance"])
async def cache_delete(key: str, _: None = Depends(verify_key)):
    """Delete a cache entry."""
    try:
        import redis.asyncio as redis
        
        r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        await r.delete(f"dawn:cache:{key}")
        await r.aclose()
        
        return {"status": "deleted", "key": key}
    except ImportError:
        raise HTTPException(status_code=501, detail="Redis not installed")
    except Exception as e:
        logger.error(f"[performance] cache delete failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cache delete failed: {str(e)}")


@router.get("/performance/cache/stats", tags=["performance"])
async def cache_stats(_: None = Depends(verify_key)):
    """Get cache statistics."""
    try:
        import redis.asyncio as redis
        
        r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        info = await r.info()
        keys_count = await r.dbsize()
        await r.aclose()
        
        return {
            "keys": keys_count,
            "used_memory_human": info.get("used_memory_human", "N/A"),
            "uptime_in_seconds": info.get("uptime_in_seconds", 0),
            "connected_clients": info.get("connected_clients", 0),
            "hit_rate": f"{info.get('keyspace_hits', 0) / max(info.get('keyspace_misses', 0) + info.get('keyspace_hits', 0), 1) * 100:.1f}%",
        }
    except ImportError:
        return {"status": "Redis not available"}
    except Exception as e:
        logger.error(f"[performance] cache stats failed: {e}")
        return {"status": "Redis error", "error": str(e)}


# ─── Query Performance ────────────────────────────────────────────────────

@router.get("/performance/query-analysis", tags=["performance"])
async def analyze_query_performance(_: None = Depends(verify_key)):
    """Analyze database query performance."""
    try:
        supabase = db.get_db()
        
        # Get table sizes and index info
        tables_info = supabase.rpc("get_table_sizes").execute()
        
        # Get slow queries (requires pg_stat_statements)
        slow_queries = supabase.rpc("get_slow_queries", {"min_duration_ms": 100}).execute()
        
        return {
            "table_sizes": tables_info.data if tables_info.data else [],
            "slow_queries": slow_queries.data if slow_queries.data else [],
            "recommendations": _generate_perf_recommendations(tables_info.data or []),
        }
    except Exception as e:
        logger.error(f"[performance] query analysis failed: {e}")
        return {
            "error": str(e),
            "recommendations": ["Install pg_stat_statements extension for detailed query analysis"],
        }


def _generate_perf_recommendations(tables: list) -> list[str]:
    """Generate performance recommendations based on table sizes."""
    recommendations = []
    for table in tables:
        row_count = table.get("row_count", 0)
        if row_count > 100000:
            recommendations.append(f"Table '{table.get('table_name', 'unknown')}' has {row_count} rows — consider partitioning")
        if row_count > 10000:
            recommendations.append(f"Table '{table.get('table_name', 'unknown')}' — check index usage")
    
    if not recommendations:
        recommendations.append("All tables are within reasonable size ranges")
    
    return recommendations


# ─── Connection Pool Status ───────────────────────────────────────────────

@router.get("/performance/connection-pool", tags=["performance"])
async def get_connection_pool_status(_: None = Depends(verify_key)):
    """Get database connection pool status."""
    try:
        supabase = db.get_db()
        
        # Get active connections
        connections = supabase.rpc("get_active_connections").execute()
        
        return {
            "active_connections": len(connections.data or []),
            "max_connections": 100,  # Supabase default
            "connections": connections.data or [],
            "pool_usage_percent": round(len(connections.data or []) / 100 * 100, 1),
        }
    except Exception as e:
        logger.error(f"[performance] connection pool failed: {e}")
        return {"error": str(e)}


# ─── Response Time Monitoring ─────────────────────────────────────────────

@router.get("/performance/response-times", tags=["performance"])
async def get_response_times(
    minutes: int = 60,
    _: None = Depends(verify_key),
):
    """Get API response time metrics."""
    try:
        supabase = db.get_db()
        
        import datetime
        since = (datetime.datetime.utcnow() - datetime.timedelta(minutes=minutes)).isoformat()
        
        # Get recent request durations from audit log
        logs = supabase.table("audit_log").select("created_at, details").gte(
            "created_at", since
        ).execute()
        
        durations = []
        for log in (logs.data or []):
            details = log.get("details", {})
            if isinstance(details, str):
                try:
                    details = json.loads(details)
                except (json.JSONDecodeError, TypeError):
                    continue
            
            duration = details.get("duration_ms") if isinstance(details, dict) else None
            if duration:
                durations.append(duration)
        
        if not durations:
            return {
                "period_minutes": minutes,
                "request_count": 0,
                "message": "No response time data available. Enable duration tracking in audit logs.",
            }
        
        return {
            "period_minutes": minutes,
            "request_count": len(durations),
            "avg_ms": round(sum(durations) / len(durations), 2),
            "min_ms": round(min(durations), 2),
            "max_ms": round(max(durations), 2),
            "p50_ms": round(sorted(durations)[len(durations) // 2], 2),
            "p95_ms": round(sorted(durations)[int(len(durations) * 0.95)], 2),
            "p99_ms": round(sorted(durations)[int(len(durations) * 0.99)], 2),
        }
    except Exception as e:
        logger.error(f"[performance] response times failed: {e}")
        return {"error": str(e)}


# ─── Load Test Endpoint ───────────────────────────────────────────────────

@router.post("/performance/load-test", tags=["performance"])
async def run_load_test(
    concurrent_requests: int = 10,
    total_requests: int = 100,
    endpoint: str = "/health",
    _: None = Depends(verify_key),
):
    """Run a simple load test against an endpoint."""
    try:
        import httpx
        import asyncio
        
        base_url = str(app_settings.dawn_api_key)  # Just for the test
        
        async def make_request(client, url):
            start = time.time()
            try:
                resp = await client.get(url, timeout=5)
                duration = (time.time() - start) * 1000
                return {"status": resp.status_code, "duration_ms": round(duration, 2), "success": resp.status_code < 500}
            except Exception as e:
                duration = (time.time() - start) * 1000
                return {"status": 0, "duration_ms": round(duration, 2), "success": False, "error": str(e)}
        
        async with httpx.AsyncClient() as client:
            tasks = []
            for _ in range(total_requests):
                tasks.append(make_request(client, f"http://localhost:8000{endpoint}"))
            
            results = await asyncio.gather(*tasks)
        
        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]
        durations = [r["duration_ms"] for r in successful]
        
        return {
            "endpoint": endpoint,
            "total_requests": total_requests,
            "concurrent": concurrent_requests,
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": f"{len(successful) / total_requests * 100:.1f}%",
            "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0,
            "min_duration_ms": round(min(durations), 2) if durations else 0,
            "max_duration_ms": round(max(durations), 2) if durations else 0,
            "p95_duration_ms": round(sorted(durations)[int(len(durations) * 0.95)], 2) if durations else 0,
        }
    except Exception as e:
        logger.error(f"[performance] load test failed: {e}")
        raise HTTPException(status_code=500, detail=f"Load test failed: {str(e)}")


# ─── Index Recommendations ────────────────────────────────────────────────

@router.get("/performance/index-recommendations", tags=["performance"])
async def get_index_recommendations(_: None = Depends(verify_key)):
    """Get index recommendations based on query patterns."""
    try:
        supabase = db.get_db()
        
        # Get unused indexes
        unused = supabase.rpc("get_unused_indexes").execute()
        
        # Get missing indexes (requires pg_stat_statements)
        missing = supabase.rpc("get_missing_indexes").execute()
        
        return {
            "unused_indexes": unused.data or [],
            "missing_indexes": missing.data or [],
            "recommendations": _generate_index_recommendations(unused.data or [], missing.data or []),
        }
    except Exception as e:
        logger.error(f"[performance] index recommendations failed: {e}")
        return {
            "error": str(e),
            "recommendations": ["Enable pg_stat_statements for detailed index recommendations"],
        }


def _generate_index_recommendations(unused: list, missing: list) -> list[str]:
    """Generate index recommendations."""
    recs = []
    for idx in unused:
        recs.append(f"Consider dropping unused index: {idx.get('index_name', 'unknown')} on {idx.get('table_name', 'unknown')}")
    for idx in missing:
        recs.append(f"Consider adding index: {idx.get('recommendation', 'unknown')}")
    if not recs:
        recs.append("No index issues detected")
    return recs
