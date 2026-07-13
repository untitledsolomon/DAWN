"use client";

import React, { useEffect, useState } from "react";
import { GitBranch, Plus, RefreshCw, X } from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import {
  listOntologyObjects,
  listOntologyRelationships,
  registerOntologyObject,
  queryOntology,
  type OntologyObjectType,
  type OntologyRelationship,
} from "@/lib/api";

export default function OntologyPage() {
  const [objects, setObjects] = useState<OntologyObjectType[]>([]);
  const [relationships, setRelationships] = useState<OntologyRelationship[]>([]);
  const [loading, setLoading] = useState(true);
  const [queryResult, setQueryResult] = useState<any>(null);
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryObject, setQueryObject] = useState("Shipment");
  const [queryFilter, setQueryFilter] = useState("");
  const [queryExpand, setQueryExpand] = useState("");
  const [queryError, setQueryError] = useState<string | null>(null);

  const [showRegisterForm, setShowRegisterForm] = useState(false);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [registering, setRegistering] = useState(false);
  const [newObjectType, setNewObjectType] = useState("");
  const [newSourceTable, setNewSourceTable] = useState("");
  const [newPrimaryKey, setNewPrimaryKey] = useState("id");

  useEffect(() => {
    void loadAll();
  }, []);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [objs, rels] = await Promise.all([listOntologyObjects(), listOntologyRelationships()]);
      setObjects(objs);
      setRelationships(rels);
      if (objs.length > 0 && !objs.some((o) => o.object_type === queryObject)) {
        setQueryObject(objs[0].object_type);
      }
    } catch (err) {
      console.error("Failed to load ontology:", err);
    } finally {
      setLoading(false);
    }
  };

  const runQuery = async () => {
    setQueryLoading(true);
    setQueryError(null);
    try {
      const filters: Record<string, string> = {};
      if (queryFilter.trim()) {
        const [key, value] = queryFilter.split("=").map((s) => s.trim());
        if (key && value) filters[key] = value;
      }
      const expand = queryExpand
        ? queryExpand.split(",").map((s) => s.trim()).filter(Boolean)
        : [];

      const data = await queryOntology({ object_type: queryObject, filters, expand, limit: 10 });
      setQueryResult(data);
    } catch (err: any) {
      setQueryError(err.message || "Query failed");
      setQueryResult(null);
    } finally {
      setQueryLoading(false);
    }
  };

  const handleRegisterObject = async (e: React.FormEvent) => {
    e.preventDefault();
    setRegisterError(null);

    if (!newObjectType.trim() || !newSourceTable.trim()) {
      setRegisterError("Object type and source table are required.");
      return;
    }

    setRegistering(true);
    try {
      await registerOntologyObject({
        object_type: newObjectType.trim(),
        source_table: newSourceTable.trim(),
        primary_key_column: newPrimaryKey.trim() || "id",
        properties: {},
      });
      setNewObjectType("");
      setNewSourceTable("");
      setNewPrimaryKey("id");
      setShowRegisterForm(false);
      await loadAll();
    } catch (err: any) {
      setRegisterError(err.message || "Failed to register object type");
    } finally {
      setRegistering(false);
    }
  };

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-6 py-3 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Ontology</h1>
            <p className="text-text-muted text-2xs">Registered object types, relationships, and live queries</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowRegisterForm((v) => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all"
            >
              <Plus size={12} /> Register object type
            </button>
            <button
              onClick={loadAll}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all"
            >
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
          {showRegisterForm && (
            <div className="bg-surface border border-rim rounded-xl p-4 max-w-2xl">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-text-primary text-xs font-semibold">Register a new object type</h2>
                <button onClick={() => setShowRegisterForm(false)} className="text-text-muted hover:text-text-primary">
                  <X size={14} />
                </button>
              </div>
              <p className="text-text-muted text-2xs mb-3">
                A data change only — no deploy needed to make the object queryable via ontology_query.
              </p>
              <form onSubmit={handleRegisterObject} className="space-y-3">
                <div className="grid sm:grid-cols-3 gap-3">
                  <div>
                    <label className="text-text-muted text-2xs font-medium block mb-1">Object type name</label>
                    <input
                      value={newObjectType}
                      onChange={(e) => setNewObjectType(e.target.value)}
                      placeholder="e.g. Client"
                      className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs font-mono outline-none focus:border-dawn/50"
                    />
                  </div>
                  <div>
                    <label className="text-text-muted text-2xs font-medium block mb-1">Backing table</label>
                    <input
                      value={newSourceTable}
                      onChange={(e) => setNewSourceTable(e.target.value)}
                      placeholder="e.g. ontology_clients"
                      className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs font-mono outline-none focus:border-dawn/50"
                    />
                  </div>
                  <div>
                    <label className="text-text-muted text-2xs font-medium block mb-1">Primary key column</label>
                    <input
                      value={newPrimaryKey}
                      onChange={(e) => setNewPrimaryKey(e.target.value)}
                      className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs font-mono outline-none focus:border-dawn/50"
                    />
                  </div>
                </div>
                {registerError && <p className="text-red-600 text-2xs">{registerError}</p>}
                <button
                  type="submit"
                  disabled={registering}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all disabled:opacity-30"
                >
                  {registering ? "Registering..." : "Register"}
                </button>
              </form>
            </div>
          )}

          {/* Object Types */}
          <section>
            <h2 className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-3">
              Registered Object Types ({objects.length})
            </h2>
            <div className="grid gap-3">
              {objects.map((obj) => (
                <div key={obj.object_type} className="bg-surface border border-rim rounded-xl p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-lg bg-dawn/10 border border-dawn/20 flex items-center justify-center flex-shrink-0">
                        <GitBranch size={12} className="text-dawn" />
                      </div>
                      <span className="text-text-primary text-sm font-semibold">{obj.object_type}</span>
                      {obj.client_id && (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-2xs font-mono bg-ember/5 text-ember border border-ember/15">
                          client-scoped
                        </span>
                      )}
                    </div>
                    <span className="text-text-muted text-2xs font-mono">{obj.source_table}</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(obj.properties || {}).map(([prop, meta]: [string, any]) => (
                      <span
                        key={prop}
                        className={`text-2xs px-2 py-0.5 rounded font-mono ${
                          meta.decision_relevant
                            ? "bg-dawn/10 text-dawn border border-dawn/15"
                            : "bg-elevated text-text-secondary border border-rim"
                        }`}
                      >
                        {prop}
                        {meta.decision_relevant && " ⚡"}
                      </span>
                    ))}
                    {Object.keys(obj.properties || {}).length === 0 && (
                      <span className="text-text-muted text-2xs italic">No property metadata registered yet</span>
                    )}
                  </div>
                </div>
              ))}
              {objects.length === 0 && !loading && (
                <p className="text-text-muted text-xs">No object types registered yet.</p>
              )}
            </div>
          </section>

          {/* Relationships */}
          <section>
            <h2 className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-3">
              Relationships ({relationships.length})
            </h2>
            <div className="grid gap-2">
              {relationships.map((rel) => (
                <div
                  key={rel.id}
                  className="bg-surface border border-rim rounded-lg px-4 py-2 text-xs flex items-center gap-2"
                >
                  <span className="text-text-primary font-medium">{rel.from_object}</span>
                  <span className="text-text-muted">→</span>
                  <span className="text-text-primary font-medium">{rel.to_object}</span>
                  <span className="text-text-muted font-mono text-2xs">({rel.relationship_name})</span>
                </div>
              ))}
              {relationships.length === 0 && !loading && (
                <p className="text-text-muted text-xs">No relationships registered yet.</p>
              )}
            </div>
          </section>

          {/* Query Preview */}
          <section className="pb-6">
            <h2 className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-3">
              Preview Ontology Query
            </h2>
            <div className="bg-surface border border-rim rounded-xl p-4">
              <div className="flex flex-wrap gap-3 mb-3">
                <select
                  value={queryObject}
                  onChange={(e) => setQueryObject(e.target.value)}
                  className="bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50"
                >
                  {objects.map((obj) => (
                    <option key={obj.object_type} value={obj.object_type}>
                      {obj.object_type}
                    </option>
                  ))}
                </select>
                <input
                  value={queryFilter}
                  onChange={(e) => setQueryFilter(e.target.value)}
                  placeholder="Filter (e.g., status=in_transit)"
                  className="flex-1 min-w-[180px] bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs font-mono outline-none focus:border-dawn/50"
                />
                <input
                  value={queryExpand}
                  onChange={(e) => setQueryExpand(e.target.value)}
                  placeholder="Expand (e.g., current_route, carrier)"
                  className="flex-1 min-w-[180px] bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs font-mono outline-none focus:border-dawn/50"
                />
                <button
                  onClick={runQuery}
                  disabled={queryLoading}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all disabled:opacity-30"
                >
                  {queryLoading ? "Running..." : "Run Query"}
                </button>
              </div>

              {queryError && <p className="text-red-600 text-2xs mb-2">{queryError}</p>}

              {queryResult && (
                <pre className="bg-elevated border border-rim rounded-lg p-3 text-2xs font-mono overflow-auto max-h-96 text-text-secondary">
                  {JSON.stringify(queryResult, null, 2)}
                </pre>
              )}
            </div>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
