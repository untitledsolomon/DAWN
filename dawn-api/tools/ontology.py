"""Ontology Query Tool — DAWN's interface to the semantic object layer.

This tool replaces raw SQL queries for business objects. It returns
typed object graphs with expanded relationships, not flat tables.

Calls decision_engine/ontology_engine.py directly — that module is the
single source of truth for what object types and relationships exist
(driven by the ontology_objects / ontology_relationships tables), so
this tool works identically for any registered domain, not just the
seeded Shipment/Route/Vendor example.
"""

from tools.base import BaseTool, ToolResult
from decision_engine.ontology_engine import query_object, list_object_types, OntologyError


class OntologyQueryTool(BaseTool):
    name = "ontology_query"
    description = (
        "Query the ontology for typed business objects. Call ontology_list_objects first "
        "if you don't know what object types are currently registered — they vary by "
        "deployment and are never fixed in advance."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "object": {
                "type": "string",
                "description": "Registered object type name, e.g. 'Shipment', 'Route'. Call ontology_list_objects to see what's available."
            },
            "filters": {
                "type": "object",
                "description": "Key-value pairs to filter by (e.g., {\"status\": \"in_transit\"})",
                "default": {}
            },
            "expand": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Relationship names to expand (e.g., [\"current_route\", \"carrier\"])",
                "default": []
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return",
                "default": 20
            },
            "client_id": {
                "type": "string",
                "description": "Client/tenant scope, if applicable. Omit for the shared/default tenant.",
                "default": None
            }
        },
        "required": ["object"]
    }

    async def run(self, **kwargs) -> ToolResult:
        try:
            result = await query_object(
                object_type=kwargs.get("object", ""),
                filters=kwargs.get("filters", {}),
                expand=kwargs.get("expand", []),
                limit=kwargs.get("limit", 20),
                client_id=kwargs.get("client_id"),
            )
            return ToolResult(success=True, output=result)
        except OntologyError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class OntologyListObjectsTool(BaseTool):
    name = "ontology_list_objects"
    description = "List all registered ontology object types and their properties. Call this before ontology_query if you don't already know what's available."
    input_schema = {
        "type": "object",
        "properties": {
            "client_id": {
                "type": "string",
                "description": "Client/tenant scope, if applicable. Omit for the shared/default tenant.",
                "default": None
            }
        },
        "required": []
    }

    async def run(self, **kwargs) -> ToolResult:
        try:
            objects = await list_object_types(client_id=kwargs.get("client_id"))
            return ToolResult(success=True, output=objects)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
