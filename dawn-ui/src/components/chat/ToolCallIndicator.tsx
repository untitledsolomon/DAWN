import { Search, GitBranch, Tag, Cpu } from "lucide-react";
import type { ToolCall } from "@/lib/types";

const ICONS: Record<string, React.ReactNode> = {
  fuzzy_search: <Search size={10} />,
  traverse: <GitBranch size={10} />,
  search_tags: <Tag size={10} />,
  semantic_search: <Cpu size={10} />,
};

interface Props {
  toolCalls: ToolCall[];
  thinking?: boolean;
}

export default function ToolCallIndicator({
  toolCalls,
  thinking,
}: Props) {
  if (!thinking && toolCalls.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5 mb-2">
      {thinking && toolCalls.length === 0 && (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-dawn/10 border border-dawn/20 text-dawn text-2xs font-mono animate-scan">
          <span className="w-1.5 h-1.5 rounded-full bg-dawn animate-pulse-slow" />
          scanning graph...
        </span>
      )}

      {toolCalls.map((tc, i) => (
        <span
          key={i}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface border border-rim text-text-secondary text-2xs font-mono animate-fade-in"
        >
          <span className="text-dawn">
            {ICONS[tc.name] ?? <Search size={10} />}
          </span>
          <span className="text-text-muted">{tc.name}</span>
          {tc.args && Object.values(tc.args)[0] ? (
            <span className="text-text-muted">
              ({String(Object.values(tc.args)[0]).slice(0, 24)})
            </span>
          ) : null}
          {tc.result_count > 0 && (
            <span className="text-dawn/70">→ {tc.result_count}</span>
          )}
        </span>
      ))}
    </div>
  );
}
