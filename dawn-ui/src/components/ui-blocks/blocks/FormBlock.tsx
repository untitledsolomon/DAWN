"use client";

import { useState } from "react";
import type { FormBlock as FormBlockT, FormField } from "@/lib/ui/schema";
import { useActions } from "../ActionContext";

function defaults(fields: FormField[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) out[f.id] = f.default ?? "";
  return out;
}

function interpolate(text: string, values: Record<string, unknown>): string {
  return text.replace(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g, (_, id: string) => {
    const v = values[id];
    return v === undefined ? "" : String(v);
  });
}

export default function FormBlock({ block }: { block: FormBlockT }) {
  const { sendPrompt, runToolAction } = useActions();
  const [values, setValues] = useState<Record<string, unknown>>(() => defaults(block.fields ?? []));
  const action = block.submit?.action;

  const submit = () => {
    if (!action) return;
    if (action.kind === "prompt" && action.text) {
      sendPrompt(interpolate(action.text, values));
    } else if (action.kind === "tool" && action.tool) {
      void runToolAction(action, block.id ?? "", values);
    }
  };

  return (
    <div className="rounded-[10px] border border-rim bg-surface overflow-hidden">
      <div className="px-3 py-2 space-y-2">
        {(block.fields ?? []).map((f) => (
          <div key={f.id}>
            <label className="text-text-secondary text-xs block mb-1" htmlFor={`form-${f.id}`}>
              {f.label}
              {f.required ? <span className="text-ember ml-0.5">*</span> : null}
            </label>
            {f.kind === "select" ? (
              <select
                id={`form-${f.id}`}
                value={String(values[f.id] ?? "")}
                onChange={(e) => setValues({ ...values, [f.id]: e.target.value })}
                className="w-full bg-surface border border-rim rounded px-2 py-1.5 text-xs text-text-primary outline-none focus:border-dawn/50"
              >
                {(f.options ?? []).map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            ) : f.kind === "toggle" ? (
              <button
                onClick={() => setValues({ ...values, [f.id]: values[f.id] ? "" : "1" })}
                className="w-9 h-5 rounded-full transition-colors relative"
                style={{ background: values[f.id] ? "#15807A" : "#E4E4E2" }}
              >
                <span
                  className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all"
                  style={{ left: values[f.id] ? 18 : 2 }}
                />
              </button>
            ) : (
              <input
                id={`form-${f.id}`}
                type={f.kind === "number" ? "number" : "text"}
                value={String(values[f.id] ?? "")}
                onChange={(e) => setValues({ ...values, [f.id]: e.target.value })}
                className="w-full bg-surface border border-rim rounded px-2.5 py-1.5 text-xs text-text-primary outline-none focus:border-dawn/50"
              />
            )}
          </div>
        ))}
      </div>
      <div className="px-3 py-2 border-t border-rim">
        {action ? (
          <button
            onClick={submit}
            className="px-3 py-1.5 rounded-[8px] text-xs font-medium bg-dawn/90 text-white hover:bg-dawn transition-all"
          >
            {block.submit?.label || "Submit"}
          </button>
        ) : (
          <p className="text-2xs text-text-muted">No action bound to this form.</p>
        )}
      </div>
    </div>
  );
}
