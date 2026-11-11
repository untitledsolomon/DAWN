"use client";

import { useState } from "react";
import type { TableBlock as TableBlockT } from "@/lib/ui/schema";

function format(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

export default function TableBlock({ block }: { block: TableBlockT }) {
  const columns = block.columns ?? [];
  const rows = block.rows ?? [];
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [asc, setAsc] = useState(true);

  const cols = columns.length
    ? columns
    : rows.length
      ? Object.keys(rows[0]).map((k) => ({ key: k, label: k }))
      : [];

  const sorted = sortKey
    ? [...rows].sort((a, b) => {
        const av = a[sortKey] ?? "";
        const bv = b[sortKey] ?? "";
        const cmp =
          typeof av === "number" && typeof bv === "number"
            ? av - bv
            : String(av).localeCompare(String(bv));
        return asc ? cmp : -cmp;
      })
    : rows;

  const toggleSort = (key: string) => {
    if (sortKey === key) setAsc(!asc);
    else {
      setSortKey(key);
      setAsc(true);
    }
  };

  return (
    <div className="overflow-x-auto rounded-[10px] border border-rim">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="bg-elevated/60">
            {cols.map((c) => (
              <th
                key={c.key}
                onClick={block.sortable ? () => toggleSort(c.key) : undefined}
                className={
                  "px-3 py-2 font-medium text-text-muted uppercase text-2xs tracking-wider whitespace-nowrap" +
                  (block.sortable ? " cursor-pointer hover:text-text-secondary" : "")
                }
              >
                {c.label}
                {sortKey === c.key && <span className="ml-1">{asc ? "↑" : "↓"}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={i} className="border-t border-rim">
              {cols.map((c) => (
                <td key={c.key} className="px-3 py-2 text-text-secondary">
                  {format(row[c.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {block.caption && (
        <div className="px-3 py-1.5 text-2xs text-text-muted border-t border-rim">
          {block.caption}
        </div>
      )}
    </div>
  );
}
