-- Decision Intelligence Migration
-- Creates ontology backing tables, metadata registry, and decision_log

-- ============================================================
-- Ontology Backing Tables (Phase 1)
-- ============================================================

-- Shipments
CREATE TABLE IF NOT EXISTS ontology_shipments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    cargo_type TEXT,
    weight_kg NUMERIC,
    value_usd NUMERIC,
    status TEXT DEFAULT 'planned' CHECK (status IN ('planned', 'in_transit', 'delayed', 'delivered', 'cancelled')),
    current_route_id UUID,
    carrier_vendor_id UUID,
    governing_contract_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Routes
CREATE TABLE IF NOT EXISTS ontology_routes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    mode TEXT CHECK (mode IN ('sea', 'air', 'road', 'rail')),
    distance_km NUMERIC,
    typical_transit_days INTEGER,
    risk_score NUMERIC DEFAULT 0,
    available BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Vendors
CREATE TABLE IF NOT EXISTS ontology_vendors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    vendor_type TEXT CHECK (vendor_type IN ('carrier', 'supplier', 'customs_broker')),
    reliability_score NUMERIC DEFAULT 0.5,
    on_time_rate NUMERIC DEFAULT 0.5,
    active_contracts_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Contracts
CREATE TABLE IF NOT EXISTS ontology_contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_id UUID REFERENCES ontology_vendors(id),
    terms_summary TEXT,
    cost_structure JSONB,
    sla_terms JSONB,
    penalty_clauses JSONB,
    start_date DATE,
    end_date DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Cost Records
CREATE TABLE IF NOT EXISTS ontology_cost_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shipment_id UUID REFERENCES ontology_shipments(id),
    category TEXT CHECK (category IN ('freight', 'customs', 'storage', 'penalty')),
    amount_usd NUMERIC,
    incurred_at TIMESTAMPTZ DEFAULT now()
);

-- Delay Events
CREATE TABLE IF NOT EXISTS ontology_delay_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shipment_id UUID REFERENCES ontology_shipments(id),
    cause TEXT CHECK (cause IN ('weather', 'customs', 'vendor', 'mechanical', 'other')),
    delay_hours NUMERIC,
    detected_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

-- Cost Centers
CREATE TABLE IF NOT EXISTS ontology_cost_centers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    department TEXT,
    budget_usd NUMERIC DEFAULT 0,
    spent_usd NUMERIC DEFAULT 0,
    period TEXT
);

-- ============================================================
-- Ontology Metadata Registry (Phase 1)
-- ============================================================

CREATE TABLE IF NOT EXISTS ontology_objects (
    object_type TEXT PRIMARY KEY,
    source_table TEXT NOT NULL,
    primary_key_column TEXT NOT NULL,
    properties JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ontology_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_object TEXT REFERENCES ontology_objects(object_type),
    to_object TEXT REFERENCES ontology_objects(object_type),
    relationship_name TEXT NOT NULL,
    join_definition JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Seed ontology objects
INSERT INTO ontology_objects (object_type, source_table, primary_key_column, properties) VALUES
    ('Shipment', 'ontology_shipments', 'id', '{"id": {"column": "id", "type": "uuid", "decision_relevant": false}, "origin": {"column": "origin", "type": "text", "decision_relevant": true}, "destination": {"column": "destination", "type": "text", "decision_relevant": true}, "cargo_type": {"column": "cargo_type", "type": "text", "decision_relevant": true}, "weight_kg": {"column": "weight_kg", "type": "numeric", "decision_relevant": false}, "value_usd": {"column": "value_usd", "type": "numeric", "decision_relevant": true}, "status": {"column": "status", "type": "text", "decision_relevant": true}}'),
    ('Route', 'ontology_routes', 'id', '{"id": {"column": "id", "type": "uuid", "decision_relevant": false}, "origin": {"column": "origin", "type": "text", "decision_relevant": true}, "destination": {"column": "destination", "type": "text", "decision_relevant": true}, "mode": {"column": "mode", "type": "text", "decision_relevant": true}, "distance_km": {"column": "distance_km", "type": "numeric", "decision_relevant": false}, "typical_transit_days": {"column": "typical_transit_days", "type": "integer", "decision_relevant": true}, "risk_score": {"column": "risk_score", "type": "numeric", "decision_relevant": true}, "available": {"column": "available", "type": "boolean", "decision_relevant": true}}'),
    ('Vendor', 'ontology_vendors', 'id', '{"id": {"column": "id", "type": "uuid", "decision_relevant": false}, "name": {"column": "name", "type": "text", "decision_relevant": true}, "vendor_type": {"column": "vendor_type", "type": "text", "decision_relevant": true}, "reliability_score": {"column": "reliability_score", "type": "numeric", "decision_relevant": true}, "on_time_rate": {"column": "on_time_rate", "type": "numeric", "decision_relevant": true}, "active_contracts_count": {"column": "active_contracts_count", "type": "integer", "decision_relevant": false}}'),
    ('Contract', 'ontology_contracts', 'id', '{"id": {"column": "id", "type": "uuid", "decision_relevant": false}, "vendor_id": {"column": "vendor_id", "type": "uuid", "decision_relevant": true}, "terms_summary": {"column": "terms_summary", "type": "text", "decision_relevant": true}, "cost_structure": {"column": "cost_structure", "type": "jsonb", "decision_relevant": true}, "sla_terms": {"column": "sla_terms", "type": "jsonb", "decision_relevant": true}, "penalty_clauses": {"column": "penalty_clauses", "type": "jsonb", "decision_relevant": true}}'),
    ('CostRecord', 'ontology_cost_records', 'id', '{"id": {"column": "id", "type": "uuid", "decision_relevant": false}, "shipment_id": {"column": "shipment_id", "type": "uuid", "decision_relevant": true}, "category": {"column": "category", "type": "text", "decision_relevant": true}, "amount_usd": {"column": "amount_usd", "type": "numeric", "decision_relevant": true}}'),
    ('DelayEvent', 'ontology_delay_events', 'id', '{"id": {"column": "id", "type": "uuid", "decision_relevant": false}, "shipment_id": {"column": "shipment_id", "type": "uuid", "decision_relevant": true}, "cause": {"column": "cause", "type": "text", "decision_relevant": true}, "delay_hours": {"column": "delay_hours", "type": "numeric", "decision_relevant": true}}'),
    ('CostCenter', 'ontology_cost_centers', 'id', '{"id": {"column": "id", "type": "uuid", "decision_relevant": false}, "name": {"column": "name", "type": "text", "decision_relevant": true}, "department": {"column": "department", "type": "text", "decision_relevant": false}, "budget_usd": {"column": "budget_usd", "type": "numeric", "decision_relevant": true}, "spent_usd": {"column": "spent_usd", "type": "numeric", "decision_relevant": true}}')
ON CONFLICT (object_type) DO NOTHING;

-- Seed ontology relationships
INSERT INTO ontology_relationships (from_object, to_object, relationship_name, join_definition) VALUES
    ('Shipment', 'Route', 'current_route', '{"from_column": "current_route_id", "to_column": "id", "cardinality": "one"}'),
    ('Shipment', 'Vendor', 'carrier', '{"from_column": "carrier_vendor_id", "to_column": "id", "cardinality": "one"}'),
    ('Shipment', 'Contract', 'governing_contract', '{"from_column": "governing_contract_id", "to_column": "id", "cardinality": "one"}'),
    ('Shipment', 'DelayEvent', 'delay_history', '{"from_column": "id", "to_column": "shipment_id", "cardinality": "many"}'),
    ('Shipment', 'CostRecord', 'costs', '{"from_column": "id", "to_column": "shipment_id", "cardinality": "many"}'),
    ('Route', 'Vendor', 'available_carriers', '{"from_column": "id", "to_column": "id", "cardinality": "many", "via": "route_vendor_assignments"}'),
    ('Vendor', 'Contract', 'contracts', '{"from_column": "id", "to_column": "vendor_id", "cardinality": "many"}'),
    ('Vendor', 'Shipment', 'shipments_handled', '{"from_column": "id", "to_column": "carrier_vendor_id", "cardinality": "many"}'),
    ('Contract', 'Vendor', 'party', '{"from_column": "vendor_id", "to_column": "id", "cardinality": "one"}'),
    ('Contract', 'Shipment', 'governed_shipments', '{"from_column": "id", "to_column": "governing_contract_id", "cardinality": "many"}')
ON CONFLICT DO NOTHING;

-- ============================================================
-- Decision Log (Phase 5 — Audit Trail)
-- ============================================================

CREATE TABLE IF NOT EXISTS decision_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_name TEXT NOT NULL,
    triggered_by TEXT NOT NULL DEFAULT 'system',
    input_snapshot JSONB NOT NULL DEFAULT '{}',
    constraint_results JSONB NOT NULL DEFAULT '[]',
    ranked_options JSONB NOT NULL DEFAULT '[]',
    recommended_option JSONB,
    llm_explanation TEXT DEFAULT '',
    data_freshness JSONB DEFAULT '{}',
    human_decision TEXT CHECK (human_decision IN ('approved', 'overridden', 'rejected')),
    human_decision_by TEXT,
    human_decision_at TIMESTAMPTZ,
    override_reason TEXT,
    executed BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_decision_log_workflow ON decision_log(workflow_name);
CREATE INDEX IF NOT EXISTS idx_decision_log_created ON decision_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decision_log_human_decision ON decision_log(human_decision);
