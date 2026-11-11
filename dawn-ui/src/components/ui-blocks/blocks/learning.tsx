"use client";

import { useState } from "react";
import clsx from "clsx";
import MathTex from "@/lib/ui/Math";
import { renderMarkdown } from "@/lib/ui/markdown";
import { evaluateOrError } from "@/lib/ui/expr";
import type {
  MathBlock as MathBlockT, PlotBlock as PlotBlockT, StepsBlock as StepsBlockT,
  QuizBlock as QuizBlockT, CardsBlock as CardsBlockT, SourcesBlock as SourcesBlockT,
  ArgumentBlock as ArgumentBlockT, GraphBlock as GraphBlockT, DiagramBlock as DiagramBlockT,
} from "@/lib/ui/schema";

// ── math ───────────────────────────────────────────────────────────────────
export function MathBlock({ block }: { block: MathBlockT }) {
  return (
    <div className="overflow-x-auto py-1">
      <MathTex tex={block.tex} display={block.display !== false} />
      {block.caption && <p className="text-2xs text-text-muted mt-1">{block.caption}</p>}
    </div>
  );
}

// ── steps ──────────────────────────────────────────────────────────────────
export function StepsBlock({ block }: { block: StepsBlockT }) {
  const [shown, setShown] = useState(block.reveal === "all" ? block.steps.length : 0);
  return (
    <div className="rounded-[10px] border border-rim bg-surface overflow-hidden">
      {block.title && <div className="px-3 py-2 text-xs font-medium text-text-primary border-b border-rim">{block.title}</div>}
      <div>
        {block.steps.slice(0, shown).map((s, i) => (
          <div key={i} className="px-3 py-2 border-b border-rim last:border-0">
            <div className="flex gap-2">
              <span className="w-5 h-5 rounded-full bg-dawn/10 text-dawn text-2xs flex items-center justify-center flex-shrink-0 font-medium">{i + 1}</span>
              <div className="min-w-0">
                <p className="text-xs font-medium text-text-primary">{s.title}</p>
                {s.hint && <p className="text-2xs text-text-muted italic mt-0.5">Hint: {s.hint}</p>}
                {s.text && <div className="text-xs text-text-secondary leading-relaxed mt-1">{renderMarkdown(s.text)}</div>}
                {s.math && <div className="mt-1 overflow-x-auto"><MathTex tex={s.math} display={false} /></div>}
              </div>
            </div>
          </div>
        ))}
      </div>
      {shown < block.steps.length && (
        <button
          onClick={() => setShown(shown + 1)}
          className="w-full px-3 py-2 text-xs text-dawn bg-dawn/5 hover:bg-dawn/10 font-medium"
        >
          Show next step
        </button>
      )}
    </div>
  );
}

// ── quiz ───────────────────────────────────────────────────────────────────
export function QuizBlock({ block, onSaveCards }: { block: QuizBlockT; onSaveCards?: (items: { front: string; back: string }[]) => void }) {
  const [state, setState] = useState<Record<string, { chosen?: number; opened?: boolean }>>({});

  const missed: { front: string; back: string }[] = [];
  let correct = 0;
  for (const q of block.questions) {
    const s = state[q.id];
    if (q.kind === "mcq") {
      if (s?.chosen === Number(q.answer)) correct += 1;
      else if (s?.chosen !== undefined) missed.push({ front: q.prompt, back: q.explanation ?? "" });
    } else if (s?.opened) {
      // self-graded short answers count once the answer is revealed (spec:
      // self-rate Missed/Partly/Got it — we count revealed as attempted).
      correct += 1;
    }
  }
  const answered = block.questions.filter((q) => q.kind === "mcq" ? state[q.id]?.chosen !== undefined : state[q.id]?.opened).length;
  const done = answered === block.questions.length;

  return (
    <div className="rounded-[10px] border border-rim bg-surface overflow-hidden">
      <div className="px-3 py-2 text-xs font-medium text-text-primary border-b border-rim">Quiz</div>
      {block.questions.map((q, qi) => {
        const s = state[q.id] ?? {};
        return (
          <div key={q.id} className="px-3 py-2 border-b border-rim">
            <p className="text-xs text-text-primary">{qi + 1}. {q.prompt} {q.kind === "short" && <span className="text-2xs text-text-muted">(write your answer, then reveal)</span>}</p>
            {q.hint && s.chosen === undefined && !s.opened && <p className="text-2xs text-text-muted italic mt-0.5">Hint: {q.hint}</p>}
            {q.kind === "mcq" ? (
              <div className="mt-2 space-y-1">
                {(q.options ?? []).map((opt, oi) => {
                  const isAnswer = s.chosen === Number(q.answer);
                  return (
                    <button
                      key={oi}
                      onClick={() => setState((p) => ({ ...p, [q.id]: { chosen: oi } }))}
                      className={clsx(
                        "w-full text-left px-2.5 py-1.5 rounded text-xs border transition-all",
                        s.chosen !== undefined && oi === Number(q.answer) ? "bg-success/10 border-success/40 text-success"
                          : s.chosen === oi ? "bg-ember/5 border-ember/40 text-ember"
                          : "bg-surface border-rim text-text-secondary hover:border-dawn/40",
                      )}
                    >
                      {opt} {s.chosen !== undefined && oi === Number(q.answer) && isAnswer ? "✓" : ""}
                    </button>
                  );
                })}
              </div>
            ) : s.opened ? (
              <p className="text-xs text-text-secondary mt-1.5">{q.answer}</p>
            ) : (
              <button
                onClick={() => setState((p) => ({ ...p, [q.id]: { opened: true } }))}
                className="mt-2 px-2.5 py-1.5 rounded text-xs border border-rim text-text-secondary hover:border-dawn/40"
              >
                Show answer
              </button>
            )}
            {s.chosen !== undefined && q.explanation && <p className="text-2xs text-text-muted mt-1.5">{q.explanation}</p>}
          </div>
        );
      })}
      {done && (
        <div className="px-3 py-2 flex items-center justify-between gap-2">
          <span className="text-xs text-text-primary">{correct} / {block.questions.length}</span>
          {missed.length > 0 && (
            <button
              onClick={() => {
                if (onSaveCards) onSaveCards(missed);
                else window.dispatchEvent(new CustomEvent("dawn:learn-save-cards", { detail: { items: missed } }));
              }}
              className="text-xs text-dawn font-medium"
            >
              Save missed as cards
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── cards ──────────────────────────────────────────────────────────────────
export function CardsBlock({ block }: { block: CardsBlockT }) {
  const [checked, setChecked] = useState<Record<number, boolean>>({});
  const add = () => {
    const items = block.items.filter((_, i) => checked[i] !== false);
    if (items.length) {
      const ev = new CustomEvent("dawn:learn-save-cards", { detail: { items } });
      window.dispatchEvent(ev);
    }
  };
  return (
    <div className="rounded-[10px] border border-rim bg-surface overflow-hidden">
      <div className="px-3 py-2 text-xs font-medium text-text-primary border-b border-rim">Proposed cards — accept what you want</div>
      {block.items.map((item, i) => (
        <label key={i} className="flex items-start gap-2 px-3 py-2 border-b border-rim cursor-pointer">
          <input
            type="checkbox"
            checked={checked[i] !== false}
            onChange={() => setChecked((p) => ({ ...p, [i]: !(p[i] !== false) }))}
            className="mt-1 accent-dawn"
          />
          <span className="text-xs text-text-secondary"><b className="text-text-primary">{item.front}</b> — {item.back}</span>
        </label>
      ))}
      <button onClick={add} className="w-full px-3 py-2 text-xs text-dawn bg-dawn/5 hover:bg-dawn/10 font-medium">
        Add {Object.values(checked).filter((v) => v).length} card(s)
      </button>
    </div>
  );
}

// ── sources ────────────────────────────────────────────────────────────────
export function SourcesBlock({ block }: { block: SourcesBlockT }) {
  const kindLabel: Record<string, string> = { web: "web", book: "book", model: "from the model's own knowledge, unchecked" };
  return (
    <div className="rounded-[10px] border border-rim bg-surface overflow-hidden">
      <div className="px-3 py-2 text-xs font-medium text-text-primary border-b border-rim">Sources</div>
      {block.items.map((s, i) => (
        <div key={i} className="px-3 py-1.5 border-b border-rim last:border-0 text-xs">
          {s.url ? (
            <a className="text-dawn hover:underline" href={s.url} target="_blank" rel="noreferrer noopener">[{s.n}] {s.title}</a>
          ) : (
            <span className="text-text-primary">[{s.n}] {s.title}</span>
          )}
          <span className={clsx("ml-2 text-2xs", s.kind === "model" ? "text-ember" : "text-text-muted")}>
            {kindLabel[s.kind ?? "web"] ?? s.kind}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── argument ───────────────────────────────────────────────────────────────
export function ArgumentBlock({ block }: { block: ArgumentBlockT }) {
  const weakest = block.assessment?.weakest;
  return (
    <div className="rounded-[10px] border border-rim bg-surface overflow-hidden">
      {block.title && <div className="px-3 py-2 text-xs font-medium text-text-primary border-b border-rim">{block.title}</div>}
      <div className="px-3 py-2">
        <ol className="space-y-1.5">
          {(block.premises ?? []).map((p) => (
            <li key={p.id} className={clsx("text-xs text-text-secondary", p.hidden && "border border-dashed border-rim rounded px-2 py-1")}>
              {p.hidden && <span className="text-2xs text-text-muted mr-1">assumed:</span>}
              {p.text}
              {weakest === p.id && <span className="ml-1 text-2xs text-ember">← weakest</span>}
            </li>
          ))}
        </ol>
        <div className="mt-2 pt-2 border-t border-rim text-xs text-text-primary font-medium">
          Therefore: {block.conclusion?.text}
        </div>
        {block.assessment?.note && <p className="mt-1 text-2xs text-text-muted">{block.assessment.note}</p>}
        {(block.objections ?? []).map((o, i) => (
          <details key={i} className="mt-2">
            <summary className="text-xs text-text-secondary cursor-pointer">Objection: {o.text}</summary>
            {o.replies.map((r, j) => <p key={j} className="text-2xs text-text-muted mt-1">— {r}</p>)}
          </details>
        ))}
      </div>
    </div>
  );
}

// ── graph (simple layered SVG, no dependency) ──────────────────────────────
export function GraphBlock({ block }: { block: GraphBlockT }) {
  const vertical = block.direction === "TB";
  const w = 220;
  const h = 140;
  const n = block.nodes.length || 1;
  const positions = block.nodes.map((nd, i) => {
    const col = vertical ? i : 0;
    const row = vertical ? 0 : i;
    return {
      x: vertical ? 40 + (i * 60) : 20,
      y: vertical ? 20 : 20 + (i * 34),
    };
  });
  return (
    <svg viewBox={`0 0 ${vertical ? 90 + (n - 1) * 60 : 220} ${vertical ? 140 : 40 + n * 34}`} className="w-full max-w-full">
      {block.edges.map((e, i) => {
        const f = block.nodes.findIndex((x) => x.id === e.from);
        const t = block.nodes.findIndex((x) => x.id === e.to);
        if (f < 0 || t < 0) return null;
        const p1 = positions[f];
        const p2 = positions[t];
        return <line key={i} x1={p1.x + 44} y1={p1.y + 18} x2={p2.x} y2={p2.y + 18} stroke="#E4E4E2" strokeWidth={1.5} />;
      })}
      {block.nodes.map((nd, i) => {
        const p = positions[i];
        return (
          <g key={nd.id}>
            <rect x={p.x} y={p.y} width={88} height={36} rx={8} fill="#FBFBFA" stroke="#15807A" strokeWidth={1} />
            <text x={p.x + 44} y={p.y + 22} textAnchor="middle" fontSize={11} fill="#16171A">{nd.label}</text>
          </g>
        );
      })}
    </svg>
  );
}

// ── plot (safe-parser function graphs) ─────────────────────────────────────
export function PlotBlock({ block }: { block: PlotBlockT }) {
  const [params, setParams] = useState<Record<string, number>>(() => {
    const out: Record<string, number> = {};
    for (const p of block.params ?? []) out[p.id] = p.default ?? p.min ?? 0;
    return out;
  });
  const xmin = block.x?.min ?? 0;
  const xmax = block.x?.max ?? 10;
  const W = 560;
  const H = 260;
  const pad = 28;

  const samples = (expr: string) => {
    const out: { x: number; y: number | null }[] = [];
    const N = 600;
    for (let i = 0; i <= N; i++) {
      const x = xmin + ((xmax - xmin) * i) / N;
      const [v] = evaluateOrError(expr, { ...params, [block.var ?? "x"]: x });
      out.push({ x, y: v });
    }
    return out;
  };

  const ys = block.series.flatMap((s) => samples(s.expr).map((p) => p.y).filter((y): y is number => y !== null && Number.isFinite(y)));
  let ymin = ys.length ? Math.min(...ys) : 0;
  let ymax = ys.length ? Math.max(...ys) : 1;
  if (ymin === ymax) { ymin -= 1; ymax += 1; }

  const sx = (x: number) => pad + ((x - xmin) / (xmax - xmin)) * (W - 2 * pad);
  const sy = (y: number) => H - pad - ((y - ymin) / (ymax - ymin)) * (H - 2 * pad);

  const pathOf = (expr: string) => {
    const pts = samples(expr);
    let d = "";
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i];
      if (p.y === null || !Number.isFinite(p.y)) { d += i > 0 ? " L " : " M "; continue; }
      const x = sx(p.x);
      const y = sy(p.y);
      d += (d === "" || d.endsWith(" M ") ? "M" : "L") + ` ${x.toFixed(1)} ${y.toFixed(1)} `;
    }
    return d.replace(/\s+$/, "");
  };

  return (
    <div className="rounded-[10px] border border-rim bg-surface p-3">
      {block.title && <p className="text-xs font-medium text-text-primary mb-2">{block.title}</p>}
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {Array.from({ length: 6 }).map((_, i) => {
          const y = ymin + ((ymax - ymin) * i) / 5;
          return <line key={i} x1={pad} y1={sy(y)} x2={W - pad} y2={sy(y)} stroke="#E4E4E2" strokeWidth={1} />;
        })}
        {block.series.map((s, i) => (
          <path key={i} d={pathOf(s.expr)} fill="none" stroke={i === 0 ? "#15807A" : "#E0A33A"} strokeWidth={2} />
        ))}
        <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} stroke="#9C9C98" />
        <line x1={pad} y1={pad} x2={pad} y2={H - pad} stroke="#9C9C98" />
      </svg>
      <div className="mt-2 flex flex-wrap gap-2">
        {(block.params ?? []).map((p) => (
          <label key={p.id} className="flex items-center gap-2 text-2xs text-text-muted">
            {p.label}
            <input
              type="range" min={p.min ?? 0} max={p.max ?? 10} step={p.step ?? 1}
              value={params[p.id] ?? p.default ?? 0}
              onChange={(e) => setParams((prev) => ({ ...prev, [p.id]: parseFloat(e.target.value) }))}
              className="accent-dawn"
            />
            <span className="font-mono">{params[p.id] ?? p.default ?? 0}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

// ── diagram (mechanics presets from meaning, not coordinates) ──────────────
export function DiagramBlock({ block }: { block: DiagramBlockT }) {
  const [params, setParams] = useState<Record<string, number>>(() => {
    const out: Record<string, number> = {};
    for (const c of block.controls ?? []) out[c.id] = c.default ?? c.min ?? 0;
    return out;
  });
  const resolve = (v: number | string): number => {
    if (typeof v === "number") return v;
    if (typeof v === "string" && v.startsWith("$") && v.slice(1) in params) return params[v.slice(1)];
    const n = parseFloat(String(v));
    return Number.isFinite(n) ? n : 0;
  };
  const angle = resolve(block.params.angle_deg ?? 0);
  const g = 9.81;
  const theta = (angle * Math.PI) / 180;

  let graphic: React.ReactNode = null;
  switch (block.kind) {
    case "incline": {
      const mass = resolve(block.params.mass_kg ?? 1);
      const mu = resolve(block.params.mu ?? 0);
      const a = g * (Math.sin(theta) - mu * Math.cos(theta));
      const wx = mass * g * Math.sin(theta);
      const wy = mass * g * Math.cos(theta);
      graphic = (
        <div className="text-center">
          <div className="text-xs text-text-secondary mb-1">Inclined plane at {angle.toFixed(0)}°</div>
          {block.params.show_values ? (
            <p className="text-2xs font-mono text-text-secondary">a = {a.toFixed(2)} m/s² · W∥ = {wx.toFixed(1)} N · W⊥ = {wy.toFixed(1)} N</p>
          ) : null}
          <svg viewBox="0 0 200 140" className="mx-auto" style={{ maxWidth: 300 }}>
            <polygon points="10,120 190,120 190,120-30" fill="#FBFBFA" stroke="#E4E4E2" />
            <text x={40} y={118} fontSize={10} fill="#16171A">{resolve(block.params.angle_deg) ?? angle.toFixed(0)}°</text>
          </svg>
        </div>
      );
      break;
    }
    case "fbd": {
      const forces = (block.params.forces as unknown as { label: string; angle_deg: number; magnitude: number }[]) ?? [];
      graphic = (
        <svg viewBox="0 0 200 200" className="mx-auto" style={{ maxWidth: 260 }}>
          <circle cx={100} cy={100} r={18} fill="#15807A" opacity={0.15} stroke="#15807A" />
          {forces.map((f, i) => {
            const a = (f.angle_deg * Math.PI) / 180;
            const scale = 30 / Math.max(1, ...(forces.map((x) => x.magnitude)));
            const len = f.magnitude * scale;
            const x2 = 100 + len * Math.cos(a);
            const y2 = 100 - len * Math.sin(a);
            return (
              <g key={i}>
                <line x1={100} y1={100} x2={x2} y2={y2} stroke="#B84D3B" strokeWidth={2} />
                <text x={(100 + x2) / 2 + 4} y={(100 + y2) / 2} fontSize={9} fill="#16171A">{f.label}</text>
              </g>
            );
          })}
        </svg>
      );
      break;
    }
    case "projectile": {
      const v0 = resolve(block.params.v0 ?? 10);
      const ang = (resolve(block.params.angle_deg ?? 45) * Math.PI) / 180;
      const vx = v0 * Math.cos(ang);
      const vy = v0 * Math.sin(ang);
      const range = (v0 * v0 * Math.sin(2 * ang)) / g;
      const apexH = (vy * vy) / (2 * g);
      const tTotal = range / vx;
      graphic = (
        <svg viewBox="0 0 260 160" className="mx-auto" style={{ maxWidth: 320 }}>
          {Array.from({ length: 24 }).map((_, i) => {
            const t = (tTotal * i) / 23;
            const x = vx * t;
            const y = vy * t - 0.5 * g * t * t;
            return <circle key={i} cx={10 + (x / range) * 240} cy={140 - (y / (apexH || 1)) * 110} r={2.4} fill="#15807A" />;
          })}
        </svg>
      );
      break;
    }
    default:
      graphic = <p className="text-2xs text-text-muted">Diagram preset "{block.kind}" not drawn in this build.</p>;
  }

  return (
    <div className="rounded-[10px] border border-rim bg-surface p-3">
      {graphic}
      <div className="mt-2 flex flex-wrap gap-2">
        {(block.controls ?? []).map((c) => (
          <label key={c.id} className="flex items-center gap-2 text-2xs text-text-muted">
            {c.label}
            <input
              type="range" min={c.min ?? 0} max={c.max ?? 60} step={c.step ?? 1}
              value={params[c.id]}
              onChange={(e) => setParams((prev) => ({ ...prev, [c.id]: parseFloat(e.target.value) }))}
              className="accent-dawn"
            />
          </label>
        ))}
      </div>
    </div>
  );
}
