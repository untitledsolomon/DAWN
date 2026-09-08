"use client";

import { lazy, Suspense } from "react";
import { BarChart3, FileText, Loader2 } from "lucide-react";
import clsx from "clsx";
import type { Artifact } from "@/lib/types";
import Pill from "@/components/ui/Pill";
import { timeAgo } from "@/lib/format";

// Lazy load the heavy renderers — only needed at runtime
const ChartRenderer = lazy(() => import("@/components/visualize/ChartRenderer"));
const ExplainerRenderer = lazy(() => import("@/components/visualize/ExplainerRenderer"));

function CardShell({
  artifact,
  generative,
  children,
}: {
  artifact: Artifact;
  generative?: boolean;
  children: React.ReactNode;
}) {
  return (
    <article
      className={clsx(
        "p-4",
        generative
          ? "border border-dashed border-rim bg-surface rounded-card"
          : "card"
      )}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          {generative && (
            <Pill tone="neutral" className="uppercase">Sandboxed</Pill>
          )}
          <span className="mono">
            {artifact.type} · {timeAgo(artifact.created_at)} ago
          </span>
        </div>
      </div>
      <h3 className="text-[13px] font-semibold text-text-primary mb-1.5">{artifact.title}</h3>
      {artifact.description && (
        <p className="text-text-secondary text-xs leading-relaxed">{artifact.description}</p>
      )}
      {children}
    </article>
  );
}

function ChartBody({ artifact }: { artifact: Artifact }) {
  return (
    <div className="mt-3.5">
      <Suspense
        fallback={
          <div className="flex items-center justify-center py-8 rounded-nested border border-rim bg-surface/50">
            <Loader2 size={16} className="text-dawn animate-spin" />
          </div>
        }
      >
        <ChartRenderer spec={artifact.spec!} title={artifact.title} />
      </Suspense>
    </div>
  );
}

function TableBody({ artifact }: { artifact: Artifact }) {
  const rows = Array.isArray(artifact.spec?.data) ? (artifact.spec!.data as Record<string, unknown>[]) : [];
  return (
    <div className="mt-3.5 overflow-x-auto rounded-nested border border-rim">
      {rows.length === 0 ? (
        <div className="px-4 py-6 text-center text-text-muted text-xs">
          No table data available.
        </div>
      ) : (
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="bg-elevated/60">
              {Object.keys(rows[0]).map((k) => (
                <th key={k} className="px-3 py-2 font-medium text-text-muted uppercase text-2xs tracking-wider">
                  {k}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-t border-rim">
                {Object.values(row).map((v, j) => (
                  <td key={j} className="px-3 py-2 text-text-secondary">
                    {String(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function ImageBody({ artifact }: { artifact: Artifact }) {
  return (
    <div className="mt-3.5 rounded-nested overflow-hidden border border-rim">
      <img src={artifact.url!} alt={artifact.title} className="w-full h-auto" />
    </div>
  );
}

function FileBody({ artifact }: { artifact: Artifact }) {
  return (
    <a
      href={artifact.url!}
      target="_blank"
      rel="noreferrer"
      className="mt-3.5 flex items-center gap-2.5 px-3.5 py-3 rounded-nested border border-rim bg-surface hover:border-dawn/40 transition-colors"
    >
      <div className="w-8 h-8 rounded-nested bg-dawn/10 border border-dawn/20 flex items-center justify-center">
        <FileText size={14} className="text-dawn" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-text-primary text-xs font-medium truncate">{artifact.title}</p>
        <p className="text-text-muted text-2xs font-mono">Download file</p>
      </div>
    </a>
  );
}

function ExplainerBody({ artifact }: { artifact: Artifact }) {
  return (
    <div className="mt-3.5">
      <Suspense
        fallback={
          <div className="flex items-center justify-center py-8 rounded-nested border border-rim bg-surface/50">
            <Loader2 size={16} className="text-dawn animate-spin" />
          </div>
        }
      >
        <ExplainerRenderer code={artifact.code!} title={artifact.title} />
      </Suspense>
    </div>
  );
}

export default function ArtifactCard({ artifact }: { artifact: Artifact }) {
  switch (artifact.type) {
    case "chart":
      return (
        <CardShell artifact={artifact}>
          {artifact.spec && <ChartBody artifact={artifact} />}
        </CardShell>
      );
    case "table":
      return (
        <CardShell artifact={artifact}>
          {artifact.spec && <TableBody artifact={artifact} />}
        </CardShell>
      );
    case "image":
      return (
        <CardShell artifact={artifact}>
          {artifact.url && <ImageBody artifact={artifact} />}
        </CardShell>
      );
    case "file":
      return (
        <CardShell artifact={artifact}>
          {artifact.url && <FileBody artifact={artifact} />}
        </CardShell>
      );
    case "explainer":
      return (
        <CardShell artifact={artifact} generative>
          {artifact.code && <ExplainerBody artifact={artifact} />}
        </CardShell>
      );
    default:
      return (
        <CardShell artifact={artifact}>
          <div className="mt-3.5 flex items-center gap-2 text-text-muted text-xs">
            <BarChart3 size={12} /> Unsupported artifact type
          </div>
        </CardShell>
      );
  }
}
