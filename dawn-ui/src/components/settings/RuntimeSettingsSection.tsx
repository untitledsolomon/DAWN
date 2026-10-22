"use client";

import { useEffect, useState } from "react";
import { RotateCcw, Save, History } from "lucide-react";
import clsx from "clsx";
import {
  getRuntimeSettings,
  setRuntimeSetting,
  resetRuntimeSetting,
  runtimeSettingHistory,
  type RuntimeSettingMeta,
} from "@/lib/api";

interface Props {
  group: string;
  title: string;
  description: string;
}

function draftFrom(meta: RuntimeSettingMeta): string {
  const v = meta.value;
  if (v === null || v === undefined) return "";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

function Row({ meta, onChanged }: { meta: RuntimeSettingMeta; onChanged: () => void }) {
  const [draft, setDraft] = useState<string>(() => draftFrom(meta));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<{ new_value: unknown; changed_by?: string; changed_at: string; reason?: string }[]>([]);

  const isList = meta.type === "list[str]";
  const isNullableFloat = meta.type === "nullable_float";
  const value = (): unknown => {
    if (meta.type === "bool") return draft === "true";
    if (isList) return draft.split(",").map((s) => s.trim()).filter(Boolean);
    if (meta.type === "int" || meta.type === "float" || isNullableFloat) {
      const t = draft.trim();
      if (t === "") return null;
      return meta.type === "int" ? parseInt(t, 10) : parseFloat(t);
    }
    return draft;
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    setOk(false);
    try {
      await setRuntimeSetting(meta.key, value());
      setOk(true);
      onChanged();
      setTimeout(() => setOk(false), 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setSaving(true);
    setError(null);
    try {
      await resetRuntimeSetting(meta.key);
      setDraft(draftFrom(meta));
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reset");
    } finally {
      setSaving(false);
    }
  };

  const toggleHistory = async () => {
    setShowHistory(!showHistory);
    if (!showHistory) {
      try {
        setHistory(await runtimeSettingHistory(meta.key));
      } catch {
        setHistory([]);
      }
    }
  };

  const badge =
    meta.source === "db" ? "changed" : meta.source === "env" ? "env" : "default";

  return (
    <div className="bg-surface border border-rim rounded-xl p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-text-primary text-sm font-medium">{meta.label}</span>
            <span
              className={clsx(
                "text-2xs font-mono px-1.5 py-0.5 rounded",
                badge === "changed" && "bg-dawn/10 text-dawn",
                badge === "env" && "bg-amber-500/10 text-amber-600",
                badge === "default" && "bg-elevated text-text-muted",
              )}
            >
              {badge}
            </span>
            {!meta.hot && (
              <span className="text-2xs font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600">
                restart required
              </span>
            )}
            <span className="text-2xs font-mono text-text-muted">{meta.key}</span>
          </div>
          <p className="text-text-muted text-xs mt-1">{meta.description}</p>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={toggleHistory}
            title="History"
            className="w-7 h-7 flex items-center justify-center rounded text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all"
          >
            <History size={13} />
          </button>
          <button
            onClick={reset}
            disabled={saving || meta.source === "env"}
            title="Reset to default"
            className="w-7 h-7 flex items-center justify-center rounded text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all disabled:opacity-30"
          >
            <RotateCcw size={13} />
          </button>
          <button
            onClick={save}
            disabled={saving}
            className={clsx(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
              ok ? "bg-success/10 text-success border border-success/20" : "bg-dawn/90 text-white hover:bg-dawn",
            )}
          >
            {ok ? "Saved" : <><Save size={11} /> Save</>}
          </button>
        </div>
      </div>

      {meta.type === "bool" ? (
        <div className="mt-3 flex items-center gap-2">
          <button
            onClick={() => setDraft(draft === "true" ? "false" : "true")}
            className={clsx(
              "w-9 h-5 rounded-full transition-colors relative",
              draft === "true" ? "bg-dawn" : "bg-rim",
            )}
          >
            <span
              className={clsx(
                "absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all",
                draft === "true" ? "left-[18px]" : "left-0.5",
              )}
            />
          </button>
          <span className="text-text-muted text-xs">{draft === "true" ? "On" : "Off"}</span>
        </div>
      ) : meta.type === "enum" ? (
        <select
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="mt-3 w-full bg-surface border border-rim rounded-lg px-3 py-2 text-sm text-text-primary outline-none focus:border-dawn/50"
        >
          {meta.choices.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      ) : (
        <div className="mt-3 flex items-center gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="flex-1 bg-surface border border-rim rounded-lg px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-dawn/50"
            type={meta.type === "int" || meta.type === "float" || isNullableFloat ? "number" : "text"}
            step={meta.step ?? undefined}
            min={meta.min ?? undefined}
            max={meta.max ?? undefined}
          />
          {meta.unit && <span className="text-text-muted text-xs flex-shrink-0">{meta.unit}</span>}
        </div>
      )}

      {showHistory && (
        <div className="mt-3 border-t border-rim pt-3 space-y-2">
          <p className="text-2xs text-text-muted font-medium uppercase tracking-wider">History</p>
          {history.length === 0 ? (
            <p className="text-text-muted text-xs">No changes yet.</p>
          ) : (
            history.map((h, i) => (
              <div key={i} className="text-xs text-text-secondary flex justify-between gap-2">
                <span className="font-mono truncate">{JSON.stringify(h.new_value ?? "reset")}</span>
                <span className="text-text-muted flex-shrink-0">{h.changed_by || "ui"} · {h.changed_at?.slice(0, 16)}</span>
              </div>
            ))
          )}
        </div>
      )}

      {error && <p className="mt-2 text-xs text-ember">{error}</p>}
    </div>
  );
}

export default function RuntimeSettingsSection({ group, title, description }: Props) {
  const [items, setItems] = useState<RuntimeSettingMeta[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    getRuntimeSettings()
      .then((all) => {
        setItems(all.filter((s) => s.group === group && (s.source === "db" || s.hot || s.source === "default")));
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [group]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-text-primary text-base font-semibold tracking-tight mb-1">{title}</h2>
        <p className="text-text-muted text-xs">{description}</p>
      </div>
      {loading ? (
        <p className="text-text-muted text-xs">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-text-muted text-xs">No tunables in this group.</p>
      ) : (
        <div className="space-y-3">
          {items.map((m) => (
            <Row key={m.key} meta={m} onChanged={load} />
          ))}
        </div>
      )}
    </div>
  );
}
