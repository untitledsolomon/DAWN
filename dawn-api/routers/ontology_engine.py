"""Generic ontology query engine.

Replaces the previous hardcoded approach in routers/decision_intelligence.py
(a Python dict mapping "Shipment" -> "ontology_shipments", and an
if/elif chain per relationship name). Every object type and relationship
this module can query comes from the ontology_objects / ontology_relationships
tables — adding a new object type or relationship is a data change
(INSERT into the registry + a backing table/view), never a code change.

Multi-tenancy: object types and relationships may carry a client_id.
NULL client_id = shared/global (today's default). When a client_id is
passed to query_object(), rows are additionally scoped by whatever
default_filter the object-type registry entry specifies for that client.
This module doesn't assume a particular tenancy shape (shared table vs.
schema-per-client) — it just applies default_filter as literal
column=value equality filters, which works for the "shared table +
client_id column" model today and can be extended later.
"""
from dataclasses import dataclass
from typing import Any, Optional
import logging

import db.client as db

logger = logging.getLogger(__name__)


class OntologyError(Exception):
    """Raised for unknown object types, unknown relationships, or bad specs."""


@dataclass
class ObjectTypeSpec:
    object_type: str
    source_table: str
    source_kind: str
    primary_key_column: str
    properties: dict
    default_filter: dict
    client_id: Optional[str]


@dataclass
class RelationshipSpec:
    from_object: str
    to_object: str
    relationship_name: str
    join_definition: dict


async def _get_object_spec(object_type: str, client_id: Optional[str] = None) -> ObjectTypeSpec:
    """Look up an object type from the registry. Never hardcode object
    type names in calling code — everything needed to query it lives here."""
    supabase = db.get_db()
    query = supabase.table("ontology_objects").select("*").eq("object_type", object_type)
    resp = await db._async_execute(lambda: query.execute())
    rows = resp.data or []

    if not rows:
        raise OntologyError(f"Unknown object type: {object_type}")

    # Prefer a client-specific registration over the shared/global one,
    # if both happen to exist for this object type.
    row = None
    if client_id:
        row = next((r for r in rows if r.get("client_id") == client_id), None)
    if row is None:
        row = next((r for r in rows if r.get("client_id") is None), rows[0])

    return ObjectTypeSpec(
        object_type=row["object_type"],
        source_table=row["source_table"],
        source_kind=row.get("source_kind", "table"),
        primary_key_column=row["primary_key_column"],
        properties=row.get("properties", {}),
        default_filter=row.get("default_filter", {}) or {},
        client_id=row.get("client_id"),
    )


async def _get_relationship_specs(from_object: str, client_id: Optional[str] = None) -> list[RelationshipSpec]:
    supabase = db.get_db()
    query = supabase.table("ontology_relationships").select("*").eq("from_object", from_object)
    resp = await db._async_execute(lambda: query.execute())
    rows = resp.data or []

    specs = []
    for row in rows:
        row_client = row.get("client_id")
        if row_client is not None and client_id is not None and row_client != client_id:
            continue
        specs.append(RelationshipSpec(
            from_object=row["from_object"],
            to_object=row["to_object"],
            relationship_name=row["relationship_name"],
            join_definition=row.get("join_definition", {}),
        ))
    return specs


async def query_object(
    object_type: str,
    filters: Optional[dict] = None,
    expand: Optional[list[str]] = None,
    limit: int = 20,
    client_id: Optional[str] = None,
) -> dict:
    """Query any registered object type, generically.

    This is the single entry point that replaces the old hardcoded
    table_map + if/elif expansion chain. Behavior for ANY object type
    (existing or newly registered) is identical — driven entirely by
    what's in ontology_objects / ontology_relationships.
    """
    filters = filters or {}
    expand = expand or []

    spec = await _get_object_spec(object_type, client_id=client_id)

    if spec.source_kind != "table":
        # 'view' behaves identically to 'table' via supabase-py today;
        # 'api' would need a distinct fetch path — not implemented until
        # a real API-backed object type is registered. Fail loudly rather
        # than silently returning nothing.
        if spec.source_kind == "api":
            raise OntologyError(
                f"Object type '{object_type}' is API-backed (source_kind='api'), "
                "which isn't wired up yet — add a fetcher in ontology_engine.py "
                "before registering API-backed object types."
            )

    supabase = db.get_db()
    query = supabase.table(spec.source_table).select("*")

    # Registry-level default filter first (e.g. tenant scoping), then
    # caller-supplied filters. Caller filters can't bypass the default
    # filter since both are applied as AND conditions.
    for key, value in {**spec.default_filter, **filters}.items():
        query = query.eq(key, value)

    resp = await db._async_execute(lambda q=query: q.limit(limit).execute())
    data = resp.data or []

    if expand:
        rel_specs = await _get_relationship_specs(object_type, client_id=client_id)
        rel_by_name = {r.relationship_name: r for r in rel_specs}
        data = await _expand_relationships(data, expand, rel_by_name, client_id=client_id)

    return {
        "object": object_type,
        "data": data,
        "count": len(data),
        "source_table": spec.source_table,
    }


async def _expand_relationships(
    rows: list[dict],
    expand: list[str],
    rel_by_name: dict[str, RelationshipSpec],
    client_id: Optional[str] = None,
) -> list[dict]:
    """Generic relationship expansion, driven by join_definition.

    join_definition shape (from ontology_relationships):
      {"from_column": "current_route_id", "to_column": "id", "cardinality": "one"}
      {"from_column": "id", "to_column": "shipment_id", "cardinality": "many"}

    cardinality "one"  -> fetch a single related row, from_column on the
                          source row points at to_column on the target table.
    cardinality "many" -> fetch all related rows where target.to_column
                          equals source.from_column's value.

    Unknown relationship names in `expand` are ignored rather than
    raising, since a caller may ask to expand several relationships and
    only some may exist for this particular object type.
    """
    enriched_rows = [dict(r) for r in rows]

    for rel_name in expand:
        rel = rel_by_name.get(rel_name)
        if not rel:
            logger.debug(f"Relationship '{rel_name}' not registered — skipping expansion")
            continue

        target_spec = await _get_object_spec(rel.to_object, client_id=client_id)
        join = rel.join_definition
        from_col = join.get("from_column")
        to_col = join.get("to_column")
        cardinality = join.get("cardinality", "one")

        if not from_col or not to_col:
            logger.warning(f"Relationship '{rel_name}' has an incomplete join_definition — skipping")
            continue

        supabase = db.get_db()

        if cardinality == "one":
            for row in enriched_rows:
                fk_value = row.get(from_col)
                if fk_value is None:
                    row[rel_name] = None
                    continue
                q = supabase.table(target_spec.source_table).select("*").eq(to_col, fk_value)
                resp = await db._async_execute(lambda q=q: q.execute())
                row[rel_name] = resp.data[0] if resp.data else None
        else:  # "many"
            for row in enriched_rows:
                pk_value = row.get(from_col)
                if pk_value is None:
                    row[rel_name] = []
                    continue
                q = supabase.table(target_spec.source_table).select("*").eq(to_col, pk_value)
                resp = await db._async_execute(lambda q=q: q.execute())
                row[rel_name] = resp.data or []

    return enriched_rows


async def list_object_types(client_id: Optional[str] = None) -> list[dict]:
    supabase = db.get_db()
    resp = await db._async_execute(lambda: supabase.table("ontology_objects").select("*").execute())
    rows = resp.data or []
    if client_id:
        rows = [r for r in rows if r.get("client_id") in (None, client_id)]
    return rows


async def list_relationships(client_id: Optional[str] = None) -> list[dict]:
    supabase = db.get_db()
    resp = await db._async_execute(lambda: supabase.table("ontology_relationships").select("*").execute())
    rows = resp.data or []
    if client_id:
        rows = [r for r in rows if r.get("client_id") in (None, client_id)]
    return rows


async def register_object_type(
    object_type: str,
    source_table: str,
    primary_key_column: str,
    properties: dict,
    source_kind: str = "table",
    default_filter: Optional[dict] = None,
    client_id: Optional[str] = None,
) -> dict:
    """Register a new object type — the ONE way new domains get added.

    This is the operation that proves the engine is generic: onboarding
    a new client's domain model (or a new object type for an existing
    client) is this single call plus a backing table/view existing —
    never a code change to this module or to routers/decision_intelligence.py.
    """
    supabase = db.get_db()
    row = {
        "object_type": object_type,
        "source_table": source_table,
        "primary_key_column": primary_key_column,
        "properties": properties,
        "source_kind": source_kind,
        "default_filter": default_filter or {},
        "client_id": client_id,
    }
    resp = await db._async_execute(
        lambda: supabase.table("ontology_objects").upsert(row, on_conflict="object_type").execute()
    )
    return resp.data[0] if resp.data else row


async def register_relationship(
    from_object: str,
    to_object: str,
    relationship_name: str,
    join_definition: dict,
    client_id: Optional[str] = None,
) -> dict:
    """Register a new relationship between two object types — a data
    change, never a code change to the expansion logic above."""
    supabase = db.get_db()
    row = {
        "from_object": from_object,
        "to_object": to_object,
        "relationship_name": relationship_name,
        "join_definition": join_definition,
        "client_id": client_id,
    }
    resp = await db._async_execute(lambda: supabase.table("ontology_relationships").insert(row).execute())
    return resp.data[0] if resp.data else row
