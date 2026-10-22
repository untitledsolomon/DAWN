"use client";

import { useState } from "react";
import type { CalcBlock as CalcBlockT, CalcInput } from "@/lib/ui/schema";
import { evaluateOrError } from "@/lib/ui/expr";

function initialValues(inputs: CalcInput[]): Record<string, number | string> {
  const out: Record<string, number | string> = {};
  for (const inp of inputs) {
    if (typeof inp.default === "number") out[inp.id] = inp.default;
    else if (typeof inp.default === "string") out[inp.id] = inp.default;
    else out[inp.id] = typeof inp.min === "number" ? inp.min : (inp.kind === "number" ? 0 : "");
  }
  return out;
}

function formatValue(v: number, format?: string): string {
  if (!Number.isFinite(v)) return "—";
  if (!format) return String(Math.round(v * 1000000) / 1000000);
  let body = format;
  let dp: number | undefined;
  const dpMatch = format.match(/^([^:]+):(\d+)$/);
  if (dpMatch) {
    body = dpMatch[1];
    dp = parseInt(dpMatch[2], 10);
  }
  if (body === "currency") {
    const iso = format.includes(":") && format.startsWith("currency:") ? format.slice("currency:".length) : "USD";
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: iso, // may be invalid for some codes — caught below
      maximumFractionDigits: dp ?? 2,
    }).format(v);
  }
  if (body === "percent") return `${(v * 100).toFixed(dp ?? 0)}%`;
  if (body === "number") return v.toFixed(dp ?? 0);
  return String(v);
}

export default function CalcBlock({ block }: { block: CalcBlockT }) {
  const [values, setValues] = useState<Record<string, number | string>>(() =>
    initialValues(block.inputs ?? []),
  );

  const setValue = (id: string, raw: number | string) => {
    setValues((prev) => ({ ...prev, [id]: raw }));
  };

  const vars: Record<string, number> = {};
  for (const [k, v] of Object.entries(values)) {
    const n = typeof v === "number" ? v : parseFloat(v);
    if (Number.isFinite(n)) vars[k] = n;
  }

  return (
    <div className="rounded-[10px] border border-rim bg-surface overflow-hidden">
      {(block.inputs ?? []).map((inp) => (
        <div key={inp.id} className="px-3 py-2 border-b border-rim flex items-center gap-3">
          <label className="text-text-secondary text-xs flex-shrink-0 w-32 truncate" htmlFor={`calc-${inp.id}`}>
            {inp.label}
          </label>
          {inp.kind === "slider" ? (
            <div className="flex items-center gap-2 flex-1">
              <input
                id={`calc-${inp.id}`}
                type="range"
                min={inp.min ?? 0}
                max={inp.max ?? 100}
                step={inp.step ?? 1}
                value={typeof values[inp.id] === "number" ? (values[inp.id] as number) : 0}
                onChange={(e) => setValue(inp.id, parseFloat(e.target.value))}
                className="flex-1 accent-dawn"
              />
              <span className="text-text-primary text-xs font-mono w-14 text-right">
                {values[inp.id]}
                {inp.unit ? ` ${inp.unit}` : ""}
              </span>
            </div>
          ) : inp.kind === "select" ? (
            <select
              id={`calc-${inp.id}`}
              value={String(values[inp.id])}
              onChange={(e) => setValue(inp.id, e.target.value)}
              className="flex-1 bg-surface border border-rim rounded px-2 py-1.5 text-xs text-text-primary outline-none"
            >
              {(inp.options ?? []).map((o) => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>
          ) : inp.kind === "toggle" ? (
            <button
              onClick={() => setValue(inp.id, values[inp.id] === "1" ? "0" : "1")}
              className="w-9 h-5 rounded-full transition-colors relative bg-rim"
              style={{ background: values[inp.id] === "1" ? "#15807A" : undefined }}
            >
              <span
                className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all"
                style={{ left: values[inp.id] === "1" ? 18 : 2 }}
              />
            </button>
          ) : (
            <input
              id={`calc-${inp.id}`}
              type="number"
              value={typeof values[inp.id] === "number" || values[inp.id] !== "" ? String(values[inp.id]) : ""}
              min={inp.min ?? undefined}
              max={inp.max ?? undefined}
              step={inp.step ?? undefined}
              onChange={(e) => setValue(inp.id, e.target.value)}
              className="flex-1 bg-surface border border-rim rounded px-2 py-1.5 text-xs font-mono text-text-primary outline-none focus:border-dawn/50"
            />
          )}
        </div>
      ))}

      <div className="px-3 py-2 space-y-1">
        {(block.outputs ?? []).map((out) => {
          const [value, error] = evaluateOrError(out.expr, vars);
          return (
            <div key={out.label} className="flex items-baseline justify-between gap-3">
              <span className="text-text-muted text-xs">{out.label}</span>
              <span className="text-text-primary text-sm font-mono font-medium">
                {error ? "—" : formatValue(value as number, out.format)}
              </span>
            </div>
          );
        })}
      </div>
      {block.note && <p className="px-3 py-1 text-2xs text-text-muted border-t border-rim">{block.note}</p>}
    </div>
  );
}
