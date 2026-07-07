"""Ontology Query Tool — DAWN's interface to the semantic object layer.

This tool replaces raw SQL queries for business objects. It returns
typed object graphs with expanded relationships, not flat tables.
"""

from ..tools.base import BaseTool, ToolResult
from ..routers.decision_intelligence import OntologyQueryRequest, query_ontology


class OntologyQueryTool(BaseTool):
    name = "ontology_query"
    description = "Query the ontology for typed business objects (Shipments, Routes, Vendors, Contracts, etc.)"
    input_schema = {
        "type": "object",
        "properties": {
            "object": {
                "type": "string",
                "description": "Object type: Shipment, Route, Vendor, Contract, CostRecord, DelayEvent, or CostCenter"
            },
            "filters": {
                "type": "object",
                "description": "Key-value pairs to filter by (e.g., {\"status\": \"in_transit\"})",
                "default": {}
            },
            "expand": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Relationship paths to expand (e.g., [\"current_route\", \"carrier\"])",
                "default": []
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return",
                "default": 20
            }
        },
        "required": ["object"]
    }

    async def run(self, **kwargs) -> ToolResult:
        try:
            req = OntologyQueryRequest(
                object_type=kwargs.get("object", ""),
                filters=kwargs.get("filters", {}),
                expand=kwargs.get("expand", []),
                limit=kwargs.get("limit", 20)
            )
            result = await query_ontology(req)
            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
