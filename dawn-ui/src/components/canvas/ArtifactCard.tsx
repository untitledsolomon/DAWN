"use client";

import { BarChart3 } from "lucide-react";
import clsx from "clsx";
import type { Artifact } from "@/lib/types";
import Pill from "@/components/ui/Pill";
import { timeAgo } from "@/lib/format";
import ArtifactBody from "@/components/canvas/ArtifactBody";

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
          ? "border border-dashed border-rim bg-surface rounded-[10px]"
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

export default function ArtifactCard({ artifact }: { artifact: Artifact }) {
  switch (artifact.type) {
    case "explainer":
      return (
        <CardShell artifact={artifact} generative>
          <ArtifactBody artifact={artifact} />
        </CardShell>
      );
    case "chart":
    case "table":
    case "image":
    case "file":
    case "markdown":
    case "note":
      return (
        <CardShell artifact={artifact}>
          <ArtifactBody artifact={artifact} />
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
