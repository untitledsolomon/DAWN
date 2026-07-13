"use client";

import React, { useEffect, useState } from "react";
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
    setLoading(true);
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
      setLoading(false);
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
    <div className="max-w-6xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">Ontology Manager</h1>

      {/* Object Types */}
      <section className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Registered Object Types ({objects.length})
          </h2>
          <button
            onClick={() => setShowRegisterForm((v) => !v)}
            className="px-3 py-1.5 text-sm font-medium text-blue-700 dark:text-blue-400 border border-blue-300 dark:border-blue-700 rounded-md hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
          >
            {showRegisterForm ? "Cancel" : "+ Register object type"}
          </button>
        </div>

        {showRegisterForm && (
          <form
            onSubmit={handleRegisterObject}
            className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 mb-4 bg-gray-50 dark:bg-gray-900 space-y-3"
          >
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Registers a new object type against an existing table. This is a data change only —
              no code deploy needed to make the object queryable via ontology_query.
            </p>
            <div className="grid sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                  Object type name
                </label>
                <input
                  type="text"
                  value={newObjectType}
                  onChange={(e) => setNewObjectType(e.target.value)}
                  placeholder="e.g. Client"
                  className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-1.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                  Backing table
                </label>
                <input
                  type="text"
                  value={newSourceTable}
                  onChange={(e) => setNewSourceTable(e.target.value)}
                  placeholder="e.g. ontology_clients"
                  className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-1.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                  Primary key column
                </label>
                <input
                  type="text"
                  value={newPrimaryKey}
                  onChange={(e) => setNewPrimaryKey(e.target.value)}
                  className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-1.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                />
              </div>
            </div>
            {registerError && <p className="text-sm text-red-600 dark:text-red-400">{registerError}</p>}
            <button
              type="submit"
              disabled={registering}
              className="px-4 py-1.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md transition-colors disabled:opacity-50"
            >
              {registering ? "Registering..." : "Register"}
            </button>
          </form>
        )}

        <div className="grid gap-3">
          {objects.map((obj) => (
            <div
              key={obj.object_type}
              className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-white dark:bg-gray-800"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-bold text-gray-900 dark:text-white">{obj.object_type}</span>
                <span className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                  {obj.source_table}
                  {obj.client_id && (
                    <span className="ml-2 px-1.5 py-0.5 rounded bg-purple-100 dark:bg-purple-900/20 text-purple-700 dark:text-purple-400 font-sans">
                      client-scoped
                    </span>
                  )}
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(obj.properties || {}).map(([prop, meta]: [string, any]) => (
                  <span
                    key={prop}
                    className={`text-xs px-2 py-0.5 rounded ${
                      meta.decision_relevant
                        ? "bg-blue-100 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400"
                        : "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400"
                    }`}
                  >
                    {prop}
                    {meta.decision_relevant && " ⚡"}
                  </span>
                ))}
                {Object.keys(obj.properties || {}).length === 0 && (
                  <span className="text-xs text-gray-400 dark:text-gray-500 italic">
                    No property metadata registered yet
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Relationships */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
          Relationships ({relationships.length})
        </h2>
        <div className="grid gap-2">
          {relationships.map((rel) => (
            <div
              key={rel.id}
              className="border border-gray-200 dark:border-gray-700 rounded-lg px-4 py-2 bg-white dark:bg-gray-800 text-sm"
            >
              <span className="font-medium text-gray-900 dark:text-white">{rel.from_object}</span>
              <span className="text-gray-500 dark:text-gray-400 mx-2">→</span>
              <span className="font-medium text-gray-900 dark:text-white">{rel.to_object}</span>
              <span className="text-gray-400 dark:text-gray-500 ml-2">({rel.relationship_name})</span>
            </div>
          ))}
        </div>
      </section>

      {/* Query Preview */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
          Preview Graph Query
        </h2>
        <div className="flex flex-wrap gap-3 mb-4">
          <select
            value={queryObject}
            onChange={(e) => setQueryObject(e.target.value)}
            className="text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-1.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
          >
            {objects.map((obj) => (
              <option key={obj.object_type} value={obj.object_type}>
                {obj.object_type}
              </option>
            ))}
          </select>
          <input
            type="text"
            value={queryFilter}
            onChange={(e) => setQueryFilter(e.target.value)}
            placeholder="Filter (e.g., status=in_transit)"
            className="text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-1.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-white flex-1 min-w-[200px]"
          />
          <input
            type="text"
            value={queryExpand}
            onChange={(e) => setQueryExpand(e.target.value)}
            placeholder="Expand (e.g., current_route, carrier)"
            className="text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-1.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-white flex-1 min-w-[200px]"
          />
          <button
            onClick={runQuery}
            disabled={loading}
            className="px-4 py-1.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md transition-colors disabled:opacity-50"
          >
            {loading ? "Running..." : "Run Query"}
          </button>
        </div>

        {queryError && (
          <p className="text-sm text-red-600 dark:text-red-400 mb-3">{queryError}</p>
        )}

        {queryResult && (
          <pre className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-gray-50 dark:bg-gray-900 text-xs overflow-auto max-h-96 text-gray-800 dark:text-gray-200">
            {JSON.stringify(queryResult, null, 2)}
          </pre>
        )}
      </section>
    </div>
  );
}
