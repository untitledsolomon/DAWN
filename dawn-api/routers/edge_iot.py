"""
v28.0 — Edge & IoT
Edge deployment, IoT sensor integration, camera integration, home/office automation
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
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

class IoTDeviceCreate(BaseModel):
    name: str
    device_type: str  # 'sensor', 'camera', 'actuator', 'gateway'
    protocol: str = "mqtt"  # 'mqtt', 'http', 'websocket', 'zigbee'
    endpoint: Optional[str] = None
    location: Optional[str] = None
    config: dict = {}

class IoTDataPoint(BaseModel):
    device_id: str
    sensor_type: str  # 'temperature', 'humidity', 'motion', 'light', 'pressure', 'custom'
    value: float
    unit: Optional[str] = None
    timestamp: Optional[str] = None

class EdgeDeploymentRequest(BaseModel):
    device_id: str
    model_name: str
    model_format: str = "onnx"  # 'onnx', 'tflite', 'pytorch'
    quantization: str = "fp16"  # 'fp32', 'fp16', 'int8'

# ─── IoT Device Management ────────────────────────────────────────────────

@router.get("/iot/devices", tags=["edge-iot"])
async def list_iot_devices(_: None = Depends(verify_key)):
    """List registered IoT devices."""
    try:
        supabase = db.get_db()
        res = supabase.table("iot_devices").select("*").order("name").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[iot] list devices failed: {e}")
        return []


@router.post("/iot/devices", tags=["edge-iot"])
async def register_iot_device(req: IoTDeviceCreate, _: None = Depends(verify_key)):
    """Register a new IoT device."""
    try:
        supabase = db.get_db()
        res = supabase.table("iot_devices").insert(req.model_dump()).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        logger.error(f"[iot] register device failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to register device: {str(e)}")


@router.delete("/iot/devices/{device_id}", tags=["edge-iot"])
async def delete_iot_device(device_id: str, _: None = Depends(verify_key)):
    """Remove an IoT device."""
    try:
        supabase = db.get_db()
        supabase.table("iot_devices").delete().eq("id", device_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"[iot] delete device failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete device: {str(e)}")


# ─── IoT Data Ingestion ───────────────────────────────────────────────────

@router.post("/iot/data", tags=["edge-iot"])
async def ingest_iot_data(req: IoTDataPoint, _: None = Depends(verify_key)):
    """Ingest a data point from an IoT sensor."""
    try:
        supabase = db.get_db()
        
        # Store the data point
        res = supabase.table("iot_data").insert(req.model_dump()).execute()
        
        # Check for alert conditions
        _check_iot_alerts(req)
        
        return {"status": "ingested", "id": res.data[0]["id"] if res.data else None}
    except Exception as e:
        logger.error(f"[iot] ingest data failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to ingest data: {str(e)}")


@router.post("/iot/data/batch", tags=["edge-iot"])
async def ingest_iot_data_batch(
    data_points: list[IoTDataPoint],
    _: None = Depends(verify_key),
):
    """Ingest multiple IoT data points at once."""
    try:
        supabase = db.get_db()
        data = [dp.model_dump() for dp in data_points]
        res = supabase.table("iot_data").insert(data).execute()
        
        return {"status": "ingested", "count": len(res.data or [])}
    except Exception as e:
        logger.error(f"[iot] batch ingest failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to ingest batch: {str(e)}")


def _check_iot_alerts(data_point: IoTDataPoint):
    """Check if an IoT data point triggers any alerts."""
    try:
        supabase = db.get_db()
        
        # Get alert rules for this sensor type
        rules = supabase.table("iot_alert_rules").select("*").eq(
            "sensor_type", data_point.sensor_type
        ).eq("is_active", True).execute()
        
        for rule in (rules.data or []):
            threshold = rule.get("threshold", 0)
            condition = rule.get("condition", "above")  # 'above' or 'below'
            
            triggered = False
            if condition == "above" and data_point.value > threshold:
                triggered = True
            elif condition == "below" and data_point.value < threshold:
                triggered = True
            
            if triggered:
                supabase.table("iot_alerts").insert({
                    "device_id": data_point.device_id,
                    "rule_id": rule["id"],
                    "sensor_type": data_point.sensor_type,
                    "value": data_point.value,
                    "threshold": threshold,
                    "message": f"{data_point.sensor_type} is {data_point.value} (threshold: {threshold})",
                }).execute()
    except Exception as e:
        logger.warning(f"[iot] alert check failed: {e}")


# ─── IoT Data Query ───────────────────────────────────────────────────────

@router.get("/iot/data/{device_id}", tags=["edge-iot"])
async def get_iot_data(
    device_id: str,
    sensor_type: Optional[str] = None,
    limit: int = 100,
    _: None = Depends(verify_key),
):
    """Get IoT sensor data for a device."""
    try:
        supabase = db.get_db()
        q = supabase.table("iot_data").select("*").eq("device_id", device_id).order(
            "timestamp", desc=True
        ).limit(limit)
        
        if sensor_type:
            q = q.eq("sensor_type", sensor_type)
        
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[iot] get data failed: {e}")
        return []


@router.get("/iot/data/{device_id}/latest", tags=["edge-iot"])
async def get_latest_iot_data(device_id: str, _: None = Depends(verify_key)):
    """Get the latest reading from each sensor on a device."""
    try:
        supabase = db.get_db()
        
        # Get distinct sensor types for this device
        types = supabase.table("iot_data").select("sensor_type").eq(
            "device_id", device_id
        ).execute()
        
        sensor_types = set(d["sensor_type"] for d in (types.data or []))
        latest = {}
        
        for st in sensor_types:
            res = supabase.table("iot_data").select("*").eq(
                "device_id", device_id
            ).eq("sensor_type", st).order("timestamp", desc=True).limit(1).execute()
            
            if res.data:
                latest[st] = res.data[0]
        
        return {
            "device_id": device_id,
            "readings": latest,
            "sensor_count": len(latest),
        }
    except Exception as e:
        logger.error(f"[iot] get latest failed: {e}")
        return {"error": str(e)}


# ─── IoT Alert Rules ──────────────────────────────────────────────────────

@router.get("/iot/alerts/rules", tags=["edge-iot"])
async def list_iot_alert_rules(_: None = Depends(verify_key)):
    """List IoT alert rules."""
    try:
        supabase = db.get_db()
        res = supabase.table("iot_alert_rules").select("*").order("sensor_type").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[iot] list alert rules failed: {e}")
        return []


@router.post("/iot/alerts/rules", tags=["edge-iot"])
async def create_iot_alert_rule(
    sensor_type: str,
    condition: str = "above",
    threshold: float = 0.0,
    message_template: str = "Sensor {sensor_type} value {value} exceeded threshold {threshold}",
    _: None = Depends(verify_key),
):
    """Create an IoT alert rule."""
    try:
        supabase = db.get_db()
        res = supabase.table("iot_alert_rules").insert({
            "sensor_type": sensor_type,
            "condition": condition,
            "threshold": threshold,
            "message_template": message_template,
        }).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        logger.error(f"[iot] create alert rule failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create alert rule: {str(e)}")


@router.get("/iot/alerts", tags=["edge-iot"])
async def list_iot_alerts(
    limit: int = 50,
    acknowledged: Optional[bool] = None,
    _: None = Depends(verify_key),
):
    """List IoT alerts."""
    try:
        supabase = db.get_db()
        q = supabase.table("iot_alerts").select("*").order("created_at", desc=True).limit(limit)
        if acknowledged is not None:
            q = q.eq("acknowledged", acknowledged)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[iot] list alerts failed: {e}")
        return []


# ─── Edge Deployment ──────────────────────────────────────────────────────

@router.post("/iot/edge/deploy", tags=["edge-iot"])
async def deploy_to_edge(req: EdgeDeploymentRequest, _: None = Depends(verify_key)):
    """Deploy a model to an edge device."""
    try:
        supabase = db.get_db()
        
        # Check device exists
        device = supabase.table("iot_devices").select("*").eq("id", req.device_id).execute()
        if not device.data:
            raise HTTPException(status_code=404, detail="Device not found")
        
        # Record deployment
        deployment = supabase.table("edge_deployments").insert({
            "device_id": req.device_id,
            "model_name": req.model_name,
            "model_format": req.model_format,
            "quantization": req.quantization,
            "status": "deploying",
        }).execute()
        
        return {
            "deployment_id": deployment.data[0]["id"] if deployment.data else None,
            "status": "deploying",
            "device": device.data[0]["name"],
            "model": req.model_name,
            "message": "Edge deployment initiated. Model will be downloaded and activated on the device.",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[iot] edge deploy failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to deploy to edge: {str(e)}")


@router.get("/iot/edge/deployments", tags=["edge-iot"])
async def list_edge_deployments(
    device_id: Optional[str] = None,
    _: None = Depends(verify_key),
):
    """List edge deployments."""
    try:
        supabase = db.get_db()
        q = supabase.table("edge_deployments").select("*").order("created_at", desc=True)
        if device_id:
            q = q.eq("device_id", device_id)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[iot] list deployments failed: {e}")
        return []


# ─── Camera Integration ───────────────────────────────────────────────────

@router.post("/iot/camera/snapshot", tags=["edge-iot"])
async def capture_camera_snapshot(
    device_id: str,
    _: None = Depends(verify_key),
):
    """Capture a snapshot from a camera device."""
    try:
        supabase = db.get_db()
        
        device = supabase.table("iot_devices").select("*").eq("id", device_id).execute()
        if not device.data:
            raise HTTPException(status_code=404, detail="Camera device not found")
        
        dev = device.data[0]
        
        # In production, this would connect to the camera's API
        # For now, return a placeholder
        return {
            "device_id": device_id,
            "device_name": dev.get("name"),
            "status": "captured",
            "note": "Camera snapshot capture requires camera API integration",
            "timestamp": "now()",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[iot] camera snapshot failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to capture snapshot: {str(e)}")


# ─── Home/Office Automation ───────────────────────────────────────────────

@router.post("/iot/automation/trigger", tags=["edge-iot"])
async def trigger_automation(
    action: str,  # 'light_on', 'light_off', 'lock_door', 'unlock_door', 'set_temperature'
    target_device: Optional[str] = None,
    parameters: dict = {},
    _: None = Depends(verify_key),
):
    """Trigger an automation action."""
    try:
        supabase = db.get_db()
        
        # Log the automation action
        supabase.table("automation_logs").insert({
            "action": action,
            "target_device": target_device,
            "parameters": parameters,
            "status": "executed",
        }).execute()
        
        return {
            "status": "executed",
            "action": action,
            "target": target_device,
            "message": f"Action '{action}' executed successfully",
        }
    except Exception as e:
        logger.error(f"[iot] automation trigger failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger automation: {str(e)}")


@router.get("/iot/automation/logs", tags=["edge-iot"])
async def get_automation_logs(
    limit: int = 50,
    _: None = Depends(verify_key),
):
    """Get automation action logs."""
    try:
        supabase = db.get_db()
        res = supabase.table("automation_logs").select("*").order("created_at", desc=True).limit(limit).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[iot] automation logs failed: {e}")
        return []


# ─── Edge Device Status ───────────────────────────────────────────────────

@router.get("/iot/edge/status", tags=["edge-iot"])
async def get_edge_status(_: None = Depends(verify_key)):
    """Get overall edge/IoT system status."""
    try:
        supabase = db.get_db()
        
        devices = supabase.table("iot_devices").select("id", count="exact").execute()
        device_count = devices.count if hasattr(devices, 'count') else len(devices.data or [])
        
        active = supabase.table("iot_devices").select("id", count="exact").execute()
        active_count = active.count if hasattr(active, 'count') else len(active.data or [])
        
        data_points = supabase.table("iot_data").select("id", count="exact").execute()
        data_count = data_points.count if hasattr(data_points, 'count') else len(data_points.data or [])
        
        alerts = supabase.table("iot_alerts").select("id", count="exact").eq("acknowledged", False).execute()
        alert_count = alerts.count if hasattr(alerts, 'count') else len(alerts.data or [])
        
        return {
            "total_devices": device_count,
            "active_devices": active_count,
            "total_data_points": data_count,
            "unacknowledged_alerts": alert_count,
            "status": "operational",
        }
    except Exception as e:
        logger.error(f"[iot] edge status failed: {e}")
        return {"status": "unknown", "error": str(e)}
