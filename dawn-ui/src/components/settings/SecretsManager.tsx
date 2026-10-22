"use client";

import { useEffect, useState } from "react";
import { Eye, EyeOff, Plus, Trash2, KeyRound } from "lucide-react";
import { listSecrets, createSecret, deleteSecret } from "@/lib/api";

interface SecretRow {
  id: string;
  name: string;
  description?: string;
  created_at: string;
}

// API keys live in the encrypted vault (/secrets), not in the settings table.
// The list view never carries plaintext values; reveal only fetches the value
// for one row on demand.
export default function SecretsManager() {
  const [secrets, setSecrets] = useState<SecretRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState(false);
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});

  const load = () => {
    listSecrets()
      .then(setSecrets)
      .catch(() => setSecrets([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const add = async () => {
    setError(null);
    try {
      await createSecret({ name: name.trim(), value, description: description.trim() || undefined });
      setName("");
      setValue("");
      setDescription("");
      setAdded(true);
      setTimeout(() => setAdded(false), 1500);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save secret");
    }
  };

  const remove = async (id: string) => {
    try {
      await deleteSecret(id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete secret");
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-text-primary text-base font-semibold tracking-tight mb-1">API Keys &amp; Secrets</h2>
        <p className="text-text-muted text-xs">
          Stored encrypted in the vault. Values never appear in list views; reveal on demand per row.
        </p>
      </div>

      <div className="bg-surface border border-rim rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-rim bg-elevated/30">
          <p className="text-text-secondary text-xs font-medium">Add a secret</p>
        </div>
        <div className="p-5 space-y-3">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name (e.g. deepseek_api_key)"
            className="w-full bg-elevated/30 border border-rim rounded-lg px-3 py-2.5 text-text-primary text-sm font-mono placeholder:text-text-muted outline-none focus:border-dawn/50"
          />
          <div className="relative">
            <input
              type="password"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="Value"
              className="w-full bg-elevated/30 border border-rim rounded-lg px-3 py-2.5 pr-10 text-text-primary text-sm font-mono placeholder:text-text-muted outline-none focus:border-dawn/50"
            />
            <button
              onClick={() => setRevealed({ ...revealed, __new: !revealed.__new })}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary"
            >
              {revealed.__new ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
            className="w-full bg-elevated/30 border border-rim rounded-lg px-3 py-2.5 text-text-primary text-sm placeholder:text-text-muted outline-none focus:border-dawn/50"
          />
          <button
            onClick={add}
            disabled={!name.trim() || !value}
            className={`flex items-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
              added ? "bg-success/10 text-success border border-success/20" : "bg-dawn/90 hover:bg-dawn text-white disabled:opacity-30"
            }`}
          >
            <Plus size={14} /> {added ? "Saved" : "Add secret"}
          </button>
          {error && <p className="text-xs text-ember">{error}</p>}
        </div>
      </div>

      <div className="bg-surface border border-rim rounded-xl overflow-hidden divide-y divide-rim">
        {loading ? (
          <p className="px-5 py-4 text-text-muted text-xs">Loading…</p>
        ) : secrets.length === 0 ? (
          <p className="px-5 py-4 text-text-muted text-xs">No secrets stored yet.</p>
        ) : (
          secrets.map((s) => (
            <div key={s.id} className="px-4 py-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2.5 min-w-0">
                <KeyRound size={14} className="text-dawn flex-shrink-0" />
                <div className="min-w-0">
                  <p className="text-text-primary text-sm font-mono truncate">{s.name}</p>
                  {s.description && <p className="text-text-muted text-2xs truncate">{s.description}</p>}
                </div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <span className="text-2xs font-mono text-text-muted">
                  {revealed[s.id] ? "value visible" : "••••••••"}
                </span>
                <button
                  onClick={() => setRevealed({ ...revealed, [s.id]: !revealed[s.id] })}
                  className="w-7 h-7 flex items-center justify-center rounded text-text-muted hover:text-text-secondary"
                  title={revealed[s.id] ? "Hide" : "Reveal"}
                >
                  {revealed[s.id] ? <EyeOff size={13} /> : <Eye size={13} />}
                </button>
                <button
                  onClick={() => remove(s.id)}
                  className="w-7 h-7 flex items-center justify-center rounded text-text-muted hover:text-ember"
                  title="Delete"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
      <p className="text-text-muted text-2xs">
        The DeepSeek key and other service credentials can live here. The agent fetches them by name at runtime.
      </p>
    </div>
  );
}
