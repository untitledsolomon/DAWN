import {
  FileText,
  GitBranch,
  Search,
  Package,
  AlertTriangle,
  Check,
  X,
} from "lucide-react";
import type { AgentTraceEntry } from "@/lib/agent-types";

const ICONS: Record<string, React.ReactNode> = {
  filesystem: <FileText size={10} />,
  git: <GitBranch size={10} />,
  web_search: <Search size={10} />,
  install_skill: <Package size={10} />,
};

function iconFor(name: string): React.ReactNode {
  if (ICONS[name]) return ICONS[name];
  if (name.startsWith("skill_")) return <Package size={10} />;
  return <FileText size={10} />;
}

interface Props {
  trace: AgentTraceEntry[];
  thinking?: boolean;
  thinkingLabel?: string;
}

export default function AgentTraceIndicator({
  trace,
  thinking,
  thinkingLabel,
}: Props) {
  if (!thinking && trace.length === 0) return null;

  return (
    <div className="flex flex-col gap-1 mb-2">
      {thinking && (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-dawn/10 border border-dawn/20 text-dawn text-2xs font-mono animate-scan w-fit">
          <span className="w-1.5 h-1.5 rounded-full bg-dawn animate-pulse-slow" />
          {thinkingLabel || "working..."}
        </span>
      )}

      {trace.map((entry, i) => {
        const pending = !entry.result;
        const success = entry.result?.success;
        const primaryArg = Object.values(entry.call.args)[0];

        return (
          <span
            key={i}
            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-surface border border-rim text-text-secondary text-2xs font-mono animate-fade-in w-fit"
          >
            <span className="text-dawn">
              {iconFor(entry.call.name)}
            </span>
            <span className="text-text-muted">
              {entry.call.name}
            </span>
            {primaryArg ? (
              <span className="text-text-muted">
                ({String(primaryArg).slice(0, 32)})
              </span>
            ) : null}
            {pending && (
              <span className="w-1.5 h-1.5 rounded-full bg-dawn/50 animate-pulse-slow" />
            )}
            {!pending && success && (
              <Check size={10} className="text-success/80" />
            )}
            {!pending && success === false && (
              <X size={10} className="text-error/80" />
            )}
          </span>
        );
      })}
    </div>
  );
}

export function AgentWarningBanner({
  warning,
}: {
  warning: string;
}) {
  return (
    <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-warning/10 border border-warning/25 text-warning text-xs mb-2">
      <AlertTriangle size={13} className="flex-shrink-0 mt-0.5" />
      <span>{warning}</span>
    </div>
  );
}
