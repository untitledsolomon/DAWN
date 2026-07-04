"""
OMNI Geospatial Dashboard Tool

Provides DAWN with direct access to OMNI's geospatial data sources:
aircraft, satellites, CCTV, earthquakes, weather, traffic, AIS ships,
and the ability to visualise data on the 3D globe.

Communicates with OMNI's Node.js MCP server at http://localhost:3100/mcp
and falls back to OMNI's REST API at http://localhost:3000/api/*.
"""

import json
import math
import logging
import httpx
from typing import Any, Optional
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

OMNI_MCP_URL = "http://localhost:3100/mcp"
OMNI_REST_URL = "http://localhost:3000/api"


# ── HTTP helpers ──────────────────────────────────────────────────────

async def _call_mcp(method: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        resp = await client.post(OMNI_MCP_URL, json=payload)
        resp.raise_for_status()
        return resp.json()


async def _call_api(path: str, params: dict | None = None) -> Any:
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{OMNI_REST_URL}/{path}"
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def _post_api(path: str, data: dict) -> Any:
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{OMNI_REST_URL}/{path}"
        resp = await client.post(url, json=data)
        resp.raise_for_status()
        return resp.json()


# ── Geo helpers ───────────────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def filter_bbox(data: list, west: float, south: float, east: float, north: float) -> list:
    results = []
    for item in data:
        if isinstance(item, dict):
            lat = item.get("lat") or item.get("latitude")
            lng = item.get("lng") or item.get("longitude") or item.get("lon")
            if lat is not None and lng is not None:
                if south <= lat <= north and west <= lng <= east:
                    results.append(item)
        elif isinstance(item, list) and len(item) >= 6:
            lat, lng = item[5], item[4]
            if lat and lng and south <= lat <= north and west <= lng <= east:
                results.append(item)
    return results


def filter_near(data: list, lat: float, lng: float, radius_km: float) -> list:
    results = []
    for item in data:
        if isinstance(item, dict):
            ilat = item.get("lat") or item.get("latitude")
            ilng = item.get("lng") or item.get("longitude") or item.get("lon")
            if ilat is not None and ilng is not None:
                d = haversine(lat, lng, ilat, ilng)
                if d <= radius_km:
                    results.append(item)
    return results


# ── Tool definition ───────────────────────────────────────────────────

class OmniTool(BaseTool):
    name = "omni"
    description = (
        "Query OMNI geospatial dashboard for aircraft, satellite, CCTV, earthquake, "
        "weather, traffic, and AIS ship data. Also plot points, routes, and areas on "
        "the 3D globe, send alerts, and cross-reference data across feeds."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "get_aircraft", "get_military", "get_satellites", "get_cctv",
                    "get_quakes", "get_ships", "get_weather", "get_traffic",
                    "get_imagery", "plot_points", "plot_route", "highlight_area",
                    "send_alert", "search", "crossref", "status",
                ],
                "description": "The OMNI operation to perform",
            },
            "west": {"type": "number", "description": "West longitude for bounding box queries"},
            "south": {"type": "number", "description": "South latitude for bounding box queries"},
            "east": {"type": "number", "description": "East longitude for bounding box queries"},
            "north": {"type": "number", "description": "North latitude for bounding box queries"},
            "lat": {"type": "number", "description": "Latitude for point-based queries"},
            "lng": {"type": "number", "description": "Longitude for point-based queries"},
            "radius_km": {"type": "number", "description": "Search radius in km (default varies by operation)"},
            "min_magnitude": {"type": "number", "description": "Minimum earthquake magnitude (default: 2.5)"},
            "query": {"type": "string", "description": "Search keyword for entity search"},
            "types": {
                "type": "array", "items": {"type": "string"},
                "description": "Entity types to search (default: all)",
            },
            "points": {
                "type": "array", "items": {"type": "object"},
                "description": "Points to plot: [{lat, lng, label?, color?, size?}]",
            },
            "waypoints": {
                "type": "array", "items": {"type": "object"},
                "description": "Route waypoints: [{lat, lng}]",
            },
            "label": {"type": "string", "description": "Label for plotted routes/areas"},
            "color": {"type": "string", "description": "Hex color for visualisations"},
            "message": {"type": "string", "description": "Alert message text"},
            "severity": {
                "type": "string", "enum": ["info", "warning", "critical"],
                "description": "Alert severity (default: info)",
            },
            "source": {"type": "string", "description": "Alert source label (default: DAWN)"},
            "crossref_type": {
                "type": "string", "enum": ["aircraft_near_quake", "satellites_over_quake", "all_near_point"],
                "description": "Type of cross-reference analysis",
            },
            "width": {"type": "number", "description": "Satellite imagery width in pixels (default: 512)"},
            "height": {"type": "number", "description": "Satellite imagery height in pixels (default: 512)"},
        },
        "required": ["operation"],
    }

    async def run(self, operation: str, **kwargs) -> ToolResult:
        try:
            handler = getattr(self, f"_op_{operation}", None)
            if not handler:
                return ToolResult(success=False, error=f"Unknown OMNI operation: {operation}")
            result = await handler(**kwargs)
            return ToolResult(success=True, output=result)
        except Exception as e:
            logger.exception(f"OMNI operation '{operation}' failed")
            return ToolResult(success=False, error=f"OMNI operation '{operation}' failed: {e}")

    # ── Operation handlers ──────────────────────────────────────────

    async def _op_status(self, **kwargs) -> dict:
        """Get OMNI system status."""
        try:
            result = await _call_mcp("status", {})
            return result.get("result", result)
        except Exception:
            try:
                health = await _call_api("health")
                return {"status": "connected", "health": health}
            except Exception as e:
                return {"status": "unavailable", "error": str(e)}

    async def _op_get_aircraft(self, west: float = -180, south: float = -90,
                                east: float = 180, north: float = 90, **kwargs) -> dict:
        """Get civil aircraft positions within a bounding box."""
        try:
            result = await _call_mcp("get_aircraft_in_bbox", {
                "west": west, "south": south, "east": east, "north": north
            })
            return result.get("result", result)
        except Exception:
            data = await _call_api("flights")
            states = data if isinstance(data, list) else data.get("states", [])
            filtered = filter_bbox(states, west, south, east, north)
            return {"count": len(filtered), "aircraft": filtered}

    async def _op_get_military(self, **kwargs) -> dict:
        """Get military aircraft positions."""
        try:
            result = await _call_mcp("get_military_aircraft", {})
            return result.get("result", result)
        except Exception:
            data = await _call_api("military")
            return data

    async def _op_get_satellites(self, lat: float = 0, lng: float = 0,
                                  radius_km: float = 500, **kwargs) -> dict:
        """Get satellites passing over a geographic point."""
        try:
            result = await _call_mcp("get_satellites_over_point", {
                "lat": lat, "lng": lng, "radius_km": radius_km
            })
            return result.get("result", result)
        except Exception:
            data = await _call_api("satellites")
            sats = data if isinstance(data, list) else data.get("satellites", [])
            filtered = filter_near(sats, lat, lng, radius_km)
            return {"count": len(filtered), "satellites": filtered}

    async def _op_get_cctv(self, lat: float = 0, lng: float = 0,
                            radius_km: float = 10, **kwargs) -> dict:
        """Get CCTV camera feeds near a location."""
        try:
            result = await _call_mcp("get_cctv_feeds_near", {
                "lat": lat, "lng": lng, "radius_km": radius_km
            })
            return result.get("result", result)
        except Exception:
            data = await _call_api("cctv")
            cams = data if isinstance(data, list) else data.get("cameras", [])
            filtered = filter_near(cams, lat, lng, radius_km)
            return {"count": len(filtered), "cameras": filtered}

    async def _op_get_quakes(self, west: float = -180, south: float = -90,
                              east: float = 180, north: float = 90,
                              min_magnitude: float = 2.5, **kwargs) -> dict:
        """Get recent earthquake activity in a region."""
        try:
            result = await _call_mcp("get_seismic_activity", {
                "west": west, "south": south, "east": east, "north": north,
                "min_magnitude": min_magnitude
            })
            return result.get("result", result)
        except Exception:
            data = await _call_api("quakes")
            features = data if isinstance(data, list) else data.get("features", [])
            filtered = filter_bbox(features, west, south, east, north)
            if min_magnitude > 0:
                filtered = [f for f in filtered
                           if (f.get("mag") or f.get("properties", {}).get("mag", 0)) >= min_magnitude]
            return {"count": len(filtered), "quakes": filtered}

    async def _op_get_ships(self, west: float = -180, south: float = -90,
                             east: float = 180, north: float = 90, **kwargs) -> dict:
        """Get AIS ship positions within a bounding box."""
        try:
            result = await _call_mcp("get_ships_in_bbox", {
                "west": west, "south": south, "east": east, "north": north
            })
            return result.get("result", result)
        except Exception:
            return {"note": "AIS data requires WebSocket connection on OMNI frontend", "ships": []}

    async def _op_get_weather(self, lat: float = 0, lng: float = 0, **kwargs) -> dict:
        """Get current weather for a location."""
        try:
            result = await _call_mcp("get_weather", {"lat": lat, "lng": lng})
            return result.get("result", result)
        except Exception:
            data = await _call_api("weather", {"lat": lat, "lng": lng})
            return data

    async def _op_get_traffic(self, lat: float = 0, lng: float = 0,
                               radius_km: float = 5, **kwargs) -> dict:
        """Get traffic data for a location."""
        try:
            result = await _call_mcp("get_traffic_data", {
                "lat": lat, "lng": lng, "radius_km": radius_km
            })
            return result.get("result", result)
        except Exception:
            data = await _call_api("uganda/traffic", {"lat": lat, "lng": lng})
            return data

    async def _op_get_imagery(self, lat: float = 0, lng: float = 0,
                               width: int = 512, height: int = 512, **kwargs) -> dict:
        """Get satellite imagery URL for a location."""
        try:
            result = await _call_mcp("get_satellite_imagery", {
                "lat": lat, "lng": lng, "width": width, "height": height
            })
            return result.get("result", result)
        except Exception:
            data = await _call_api("imagery", {"lat": lat, "lng": lng, "width": width, "height": height})
            return data

    async def _op_plot_points(self, points: list = None, **kwargs) -> dict:
        """Plot custom points on the OMNI globe."""
        if not points:
            return {"error": "points array is required"}
        try:
            result = await _call_mcp("plot_points", {"points": points})
            return result.get("result", result)
        except Exception:
            data = await _post_api("dawn/overlay", {"type": "points", "data": points})
            return data

    async def _op_plot_route(self, waypoints: list = None, label: str = "",
                              color: str = "#00ff00", **kwargs) -> dict:
        """Plot a route/path on the OMNI globe."""
        if not waypoints:
            return {"error": "waypoints array is required"}
        try:
            result = await _call_mcp("plot_route", {
                "waypoints": waypoints, "label": label, "color": color
            })
            return result.get("result", result)
        except Exception:
            data = await _post_api("dawn/overlay", {
                "type": "route",
                "data": {"waypoints": waypoints, "label": label, "color": color}
            })
            return data

    async def _op_highlight_area(self, west: float = 0, south: float = 0,
                                  east: float = 0, north: float = 0,
                                  label: str = "", color: str = "#ff00ff", **kwargs) -> dict:
        """Highlight a geographic area on the OMNI globe."""
        try:
            result = await _call_mcp("highlight_area", {
                "west": west, "south": south, "east": east, "north": north,
                "label": label, "color": color
            })
            return result.get("result", result)
        except Exception:
            data = await _post_api("dawn/overlay", {
                "type": "area",
                "data": {
                    "bbox": {"west": west, "south": south, "east": east, "north": north},
                    "label": label, "color": color
                }
            })
            return data

    async def _op_send_alert(self, message: str = "", severity: str = "info",
                              source: str = "DAWN", **kwargs) -> dict:
        """Send an alert to the OMNI event log."""
        if not message:
            return {"error": "message is required"}
        try:
            result = await _call_mcp("send_alert", {
                "message": message, "severity": severity, "source": source
            })
            return result.get("result", result)
        except Exception:
            data = await _post_api("dawn/alert", {
                "message": message, "severity": severity, "source": source
            })
            return data

    async def _op_search(self, query: str = "", types: list = None, **kwargs) -> dict:
        """Search all entities by keyword across all data layers."""
        if not query:
            return {"error": "query is required"}
        try:
            result = await _call_mcp("search_entities", {
                "query": query, "types": types or []
            })
            return result.get("result", result)
        except Exception:
            return {"note": "Search fallback not implemented via REST", "query": query}

    async def _op_crossref(self, crossref_type: str = "", lat: float = None,
                            lng: float = None, radius_km: float = None, **kwargs) -> dict:
        """Cross-reference data across feeds."""
        if not crossref_type:
            return {"error": "crossref_type is required"}
        try:
            params = {"type": crossref_type}
            if lat is not None: params["lat"] = lat
            if lng is not None: params["lng"] = lng
            if radius_km is not None: params["radius_km"] = radius_km
            result = await _call_mcp("crossref", params)
            return result.get("result", result)
        except Exception:
            params = {"type": crossref_type}
            if lat is not None: params["lat"] = lat
            if lng is not None: params["lng"] = lng
            if radius_km is not None: params["radius_km"] = radius_km
            data = await _call_api("crossref", params)
            return data
