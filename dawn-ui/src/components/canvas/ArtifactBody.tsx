"use client";

import { lazy, Suspense } from "react";
import { FileText, Loader2 } from "lucide-react";
import { renderMarkdown } from "@/lib/ui/markdown";
import UIRenderer from "@/components/ui-blocks/UIRenderer";
import { ActionContextProvider } from "@/components/ui-blocks/ActionContext";
import type { UIDoc } from "@/lib/ui/schema";

// Lazy load the heavy renderers — only needed at runtime.
const ChartRenderer = lazy(() => import("@/components/visualize/ChartRenderer"));
const ExplainerRenderer = lazy(() => import("@/components/visualize/ExplainerRenderer"));

// Minimal shape both `Artifact` (canvas feed) and `ArtifactRef` (chat messages)
// satisfy, so the same body works inline and in the artifact feed.
export interface ArtifactBodyProps {
  artifact: {
    type: string;
    title?: string;
    spec?: Record<string, unknown> | null;
    code?: string | null;
    url?: string | null;
  };
}

function ChartBody({ artifact }: ArtifactBodyProps) {
  return (
    <div className="mt-3.5">
      <Suspense
        fallback={
          <div className="flex items-center justify-center py-8 rounded-[8px] border border-rim bg-surface/50">
            <Loader2 size={16} className="text-dawn animate-spin" />
          </div>
        }
      >
        <ChartRenderer spec={artifact.spec!} title={artifact.title} />
      </Suspense>
    </div>
  );
}

function TableBody({ artifact }: ArtifactBodyProps) {
  const rows = Array.isArray(artifact.spec?.data)
    ? (artifact.spec!.data as Record<string, unknown>[])
    : [];
  return (
    <div className="mt-3.5 overflow-x-auto rounded-[8px] border border-rim">
      {rows.length === 0 ? (
        <div className="px-4 py-6 text-center text-text-muted text-xs">
          No table data available.
        </div>
      ) : (
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="bg-elevated/60">
              {Object.keys(rows[0]).map((k) => (
                <th
                  key={k}
                  className="px-3 py-2 font-medium text-text-muted uppercase text-2xs tracking-wider"
                >
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

function ImageBody({ artifact }: ArtifactBodyProps) {
  return (
    <div className="mt-3.5 rounded-[8px] overflow-hidden border border-rim">
      <img src={artifact.url!} alt={artifact.title ?? "Image"} className="w-full h-auto" />
    </div>
  );
}

function FileBody({ artifact }: ArtifactBodyProps) {
  return (
    <a
      href={artifact.url!}
      target="_blank"
      rel="noreferrer"
      className="mt-3.5 flex items-center gap-2.5 px-3.5 py-3 rounded-[8px] border border-rim bg-surface hover:border-dawn/40 transition-colors"
    >
      <div className="w-8 h-8 rounded-[8px] bg-dawn/10 border border-dawn/20 flex items-center justify-center">
        <FileText size={14} className="text-dawn" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-text-primary text-xs font-medium truncate">{artifact.title}</p>
        <p className="text-text-muted text-2xs font-mono">Download file</p>
      </div>
    </a>
  );
}

function MarkdownBody({ artifact }: ArtifactBodyProps) {
  return (
    <div className="mt-3.5 prose prose-sm prose-invert max-w-none text-text-secondary text-xs leading-relaxed">
      {renderMarkdown(artifact.code ?? "")}
    </div>
  );
}

function ExplainerBody({ artifact }: ArtifactBodyProps) {
  return (
    <div className="mt-3.5">
      <Suspense
        fallback={
          <div className="flex items-center justify-center py-8 rounded-[8px] border border-rim bg-surface/50">
            <Loader2 size={16} className="text-dawn animate-spin" />
          </div>
        }
      >
        <ExplainerRenderer code={artifact.code!} title={artifact.title} />
      </Suspense>
    </div>
  );
}

function UiBody({ artifact }: ArtifactBodyProps) {
  const doc = artifact.spec as unknown as UIDoc;
  if (!doc || typeof doc !== "object" || !Array.isArray(doc.blocks)) return null;
  return (
    <div className="mt-3.5">
      <ActionContextProvider>
        <UIRenderer doc={doc} />
      </ActionContextProvider>
    </div>
  );
}

/**
 * Renders the body of an artifact by type. Used inline in chat messages and
 * inside ArtifactCard's shell in the canvas feed, so every type renders in
 * both places.
 */
export default function ArtifactBody({ artifact }: ArtifactBodyProps) {
  switch (artifact.type) {
    case "chart":
      return artifact.spec ? <ChartBody artifact={artifact} /> : null;
    case "table":
      return artifact.spec ? <TableBody artifact={artifact} /> : null;
    case "image":
      return artifact.url ? <ImageBody artifact={artifact} /> : null;
    case "file":
      return artifact.url ? <FileBody artifact={artifact} /> : null;
    case "markdown":
    case "note":
      return artifact.code ? <MarkdownBody artifact={artifact} /> : null;
    case "explainer":
      return artifact.code ? <ExplainerBody artifact={artifact} /> : null;
    case "ui":
      return artifact.spec ? <UiBody artifact={artifact} /> : null;
    default:
      return null;
  }
}
