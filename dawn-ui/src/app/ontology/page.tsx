"use client";

import React, { useEffect, useState } from "react";

interface OntologyObject {
  object_type: string;
  source_table: string;
  properties: Record<string, any>;
}

interface OntologyRelationship {
  id: string;
  from_object: string;
  to_object: string;
  relationship_name: string;
  join_definition: Record<string, any>;
}

export default function OntologyPage() {
  const [objects, setObjects] = useState<OntologyObject[]>([]);
  const [relationships, setRelationships] = useState<OntologyRelationship[]>([]);
  const [loading, setLoading] = useState(true);
  const [queryResult, setQueryResult] = useState<any>(null);
  const [queryObject, setQueryObject] = useState("Shipment");
  const [queryFilter, setQueryFilter] = useState("");
  const [queryExpand, setQueryExpand] = useState("");

  useEffect(() => {
    fetchObjects();
    fetchRelationships();
  }, []);

  const fetchObjects = async () => {
    try {
      const resp = await fetch("/api/ontology/objects");
      const data = await resp.json();
      setObjects(data.data || []);
    } catch (err) {
      console.error("Failed to fetch ontology objects:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchRelationships = async () => {
    try {
      const resp = await fetch("/api/ontology/relationships");
      const data = await resp.json();
      setRelationships(data.data || []);
    } catch (err) {
      console.error("Failed to fetch relationships:", err);
    }
  };

  const runQuery = async () => {
    setLoading(true);
    try {
      const filters: Record<string, string> = {};
      if (queryFilter.trim()) {
        const [key, value] = queryFilter.split("=").map((s) => s.trim());
        if (key && value) filters[key] = value;
      }

      const expand = queryExpand
        ? queryExpand.split(",").map((s) => s.trim()).filter(Boolean)
        : [];

      const resp = await fetch("/api/ontology/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ object_type: queryObject, filters, expand, limit: 10 }),
      });
      const data = await resp.json();
      setQueryResult(data);
    } catch (err) {
      console.error("Query failed:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">Ontology Manager</h1>

      {/* Object Types */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
          Registered Object Types ({objects.length})
        </h2>
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
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(obj.properties).map(([prop, meta]: [string, any]) => (
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

        {queryResult && (
          <pre className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-gray-50 dark:bg-gray-900 text-xs overflow-auto max-h-96 text-gray-800 dark:text-gray-200">
            {JSON.stringify(queryResult, null, 2)}
          </pre>
        )}
      </section>
    </div>
  );
}
