import { AlertTriangle } from "lucide-react";
import type { AgentTraceEntry } from "@/lib/agent-types";
import ToolCallView from "./ToolCallView";

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
  // Delegate to the shared rich, collapsible tool-call view.
  return (
    <div className="mb-1">
      <ToolCallView trace={trace} thinking={thinking} />
      {thinking && (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-dawn/10 border border-dawn/20 text-dawn text-2xs font-mono animate-scan w-fit">
          <span className="w-1.5 h-1.5 rounded-full bg-dawn animate-pulse-slow" />
          {thinkingLabel || "working..."}
        </span>
      )}
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
