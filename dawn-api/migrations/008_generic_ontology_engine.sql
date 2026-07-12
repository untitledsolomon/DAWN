-- ============================================================
-- MIGRATION 008: Generic Ontology Engine + Data-Driven Workflows
-- ============================================================
-- Replaces the hardcoded Shipment/Route/Vendor object model with a
-- metadata-driven object/relationship layer, and replaces one-file-
-- per-workflow Python with data-defined workflows interpreted by a
-- generic constraint engine.
--
-- Design principles:
--   1. ontology_objects / ontology_relationships are the ONLY source
--      of truth for what object types and relationships exist. No
--      object-type name should ever be hardcoded in application code.
--   2. Tenancy: every object-type and workflow row gets a nullable
--      client_id. NULL = shared/global (today's single-tenant reality).
--      A real client_id can be added later without a schema change —
--      only a column being populated. `clients` table is minimal on
--      purpose; expand later if you need billing/plan/etc.
--   3. Old ontology_shipments / ontology_routes / etc. tables from
--      migration 003_decision_intelligence.sql are left in place as
--      the BACKING DATA for the seeded 'Shipment' etc. object types —
--      they are now just one example dataset, not the model itself.
-- ============================================================

-- ============================================================
-- Tenancy groundwork
-- ============================================================

CREATE TABLE IF NOT EXISTS clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Implicit default client so existing single-tenant data has somewhere
-- to point once client_id starts being enforced. Not required today —
-- NULL client_id is treated as "shared/global" everywhere below — but
-- having a row ready means switching a given object type over to real
-- per-client scoping later is a data change, not a migration.
INSERT INTO clients (name, slug)
VALUES ('Regent', 'regent')
ON CONFLICT (slug) DO NOTHING;

ALTER TABLE ontology_objects
    ADD COLUMN IF NOT EXISTS client_id UUID REFERENCES clients(id);

ALTER TABLE ontology_relationships
    ADD COLUMN IF NOT EXISTS client_id UUID REFERENCES clients(id);

-- ============================================================
-- Generic object registry — extend existing ontology_objects
-- ============================================================
-- source_table already exists (migration 003). Add source_kind so the
-- registry can eventually back an object type with something other
-- than a 1:1 dedicated table (a shared multi-tenant table filtered by
-- client_id, a view, or an external API) without another migration.

ALTER TABLE ontology_objects
    ADD COLUMN IF NOT EXISTS source_kind TEXT NOT NULL DEFAULT 'table'
        CHECK (source_kind IN ('table', 'view', 'api'));

-- Default filter applied on every query for this object type, e.g.
-- {"client_id": "<uuid>"} for a shared table scoped to one tenant.
-- NULL/empty = no implicit filter (today's default).
ALTER TABLE ontology_objects
    ADD COLUMN IF NOT EXISTS default_filter JSONB NOT NULL DEFAULT '{}';

COMMENT ON TABLE ontology_objects IS
    'Generic object-type registry. query_ontology() reads source_table, '
    'primary_key_column, properties, and default_filter from here at query '
    'time — no object type name should be hardcoded in application code. '
    'Adding a new object type is an INSERT here (+ backing table/view), '
    'never a code change.';

COMMENT ON TABLE ontology_relationships IS
    'Generic relationship registry. join_definition (from_column, '
    'to_column, cardinality, optional via) is executed generically by '
    'the ontology query engine — relationship names are never hardcoded '
    'in application code.';

-- ============================================================
-- Data-driven workflows (replaces one .py file per workflow)
-- ============================================================
-- A workflow is now a row: a name, the object type it operates over,
-- a list of constraints (hard + soft, as data), and how to build
-- candidate options. The constraint engine (decision_engine/) is
-- rewritten to interpret these generically instead of importing a
-- hand-written Python handler per workflow.

CREATE TABLE IF NOT EXISTS ontology_workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    client_id UUID REFERENCES clients(id),  -- NULL = shared/global workflow
    requires_approval BOOLEAN NOT NULL DEFAULT true,
    -- Which object type this workflow ranks candidates of, e.g. "Route".
    candidate_object_type TEXT REFERENCES ontology_objects(object_type),
    -- How to fetch candidates given workflow inputs. Interpreted generically
    -- by decision_engine/candidates.py. Example:
    -- {"strategy": "ontology_query", "object": "Route",
    --  "filters_from_inputs": {"available": true}}
    candidate_source JSONB NOT NULL DEFAULT '{}',
    -- List of constraint specs, each interpreted generically by
    -- decision_engine/constraint_interpreter.py. Example entry:
    -- {"name": "budget_ceiling", "type": "hard",
    --  "rule": "field_lte", "field": "projected_cost",
    --  "compare_to": {"input": "shipment_value", "multiplier": 0.15}}
    constraints JSONB NOT NULL DEFAULT '[]',
    input_schema JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ontology_workflows_client ON ontology_workflows(client_id);

-- ============================================================
-- Seed: the existing reroute_shipment logic, expressed as data
-- ============================================================
-- This is the proof that the generic engine reproduces the original
-- hardcoded workflow with zero Python beyond the interpreter itself.
-- client_id is NULL (shared/global) since there's only one tenant today.

INSERT INTO ontology_workflows (
    name, description, requires_approval, candidate_object_type,
    candidate_source, constraints, input_schema
) VALUES (
    'reroute_shipment',
    'Given a shipment needing rerouting, rank candidate routes/carriers by contract compliance, budget, transit time, reliability, and cost.',
    true,
    'Route',
    '{"strategy": "inputs_field", "field": "candidate_routes"}',
    '[
        {
            "name": "contract_compliance",
            "type": "hard",
            "rule": "field_truthy",
            "field": "has_active_contract",
            "explanation_true": "Carrier has active contract",
            "explanation_false": "No active contract for this cargo type"
        },
        {
            "name": "budget_ceiling",
            "type": "hard",
            "rule": "field_lte",
            "field": "projected_cost",
            "compare_to": {"input": "shipment_value", "multiplier": 0.15},
            "explanation_template": "${field} vs ceiling ${compare_to} (15% of shipment value)"
        },
        {
            "name": "transit_time",
            "type": "soft",
            "weight": 0.4,
            "rule": "minimize_ratio",
            "field": "transit_days",
            "max_value": 30,
            "explanation_template": "{field} days transit"
        },
        {
            "name": "reliability",
            "type": "soft",
            "weight": 0.4,
            "rule": "maximize_field",
            "field": "on_time_rate",
            "explanation_template": "On-time rate: {field}"
        },
        {
            "name": "cost",
            "type": "soft",
            "weight": 0.2,
            "rule": "minimize_ratio",
            "field": "projected_cost",
            "max_value_field": "max_acceptable_cost",
            "max_value_default": 100000,
            "explanation_template": "${field} projected cost"
        }
    ]'::jsonb,
    '{"shipment_id": {"type": "string", "required": true}, "reason": {"type": "string", "required": false}, "candidate_routes": {"type": "array", "required": true}}'::jsonb
)
ON CONFLICT (name) DO NOTHING;

-- ============================================================
-- Fix: undefined 'preference' node type referenced in application code
-- (routers/chat.py, tools/knowledge_graph.py, routers/dev_experience.py)
-- but never added to the enum. Add it so those checks/inserts work.
-- ============================================================

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_enum
    WHERE enumlabel = 'preference'
      AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'node_type')
  ) THEN
    ALTER TYPE node_type ADD VALUE 'preference';
  END IF;
END $$;

NOTIFY pgrst, 'reload schema';
