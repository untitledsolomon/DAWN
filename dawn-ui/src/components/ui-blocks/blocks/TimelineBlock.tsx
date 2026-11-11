import clsx from "clsx";
import type { TimelineBlock as TimelineBlockT } from "@/lib/ui/schema";

const STATUS_DOT = {
  done: "bg-success",
  active: "bg-dawn",
  pending: "bg-text-muted/50",
  failed: "bg-ember",
} as const;

export default function TimelineBlock({ block }: { block: TimelineBlockT }) {
  return (
    <ol className="space-y-0">
      {(block.items ?? []).map((item, i) => (
        <li key={i} className="relative flex gap-3 pb-3 last:pb-0">
          {i < (block.items ?? []).length - 1 && (
            <span className="absolute left-[5px] top-3.5 bottom-0 w-px bg-rim" />
          )}
          <span
            className={clsx(
              "relative z-10 mt-1.5 w-2.5 h-2.5 rounded-full flex-none",
              STATUS_DOT[item.status ?? "pending"] ?? "bg-text-muted/50",
            )}
          />
          <div className="min-w-0">
            <div className="flex items-baseline gap-2">
              <span className="text-xs font-medium text-text-primary">{item.title}</span>
              <span className="text-2xs text-text-muted font-mono flex-shrink-0">{item.time}</span>
            </div>
            {item.detail && (
              <p className="text-xs text-text-secondary mt-0.5">{item.detail}</p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
