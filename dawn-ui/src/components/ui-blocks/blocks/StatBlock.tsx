import clsx from "clsx";
import type { StatBlock as StatBlockT } from "@/lib/ui/schema";

export default function StatBlock({ block }: { block: StatBlockT }) {
  const delta = block.delta;
  const num = typeof block.value === "number" ? block.value : null;
  let arrow: string | null = null;
  if (delta) {
    if (delta.value > 0) arrow = "↑";
    else if (delta.value < 0) arrow = "↓";
  }
  const goodDir = delta?.good;
  const isGood =
    goodDir === undefined ? undefined : delta?.direction === goodDir;
  return (
    <div className="p-3 rounded-[10px] border border-rim bg-surface">
      <div className="text-2xs text-text-muted font-medium uppercase tracking-wider">
        {block.label}
      </div>
      <div className="mt-0.5 flex items-baseline gap-1.5">
        <span className="text-xl font-semibold text-text-primary tracking-tight">
          {num !== null ? num.toLocaleString() : String(block.value)}
        </span>
        {block.unit && <span className="text-xs text-text-muted">{block.unit}</span>}
        {arrow && (
          <span
            className={clsx(
              "text-xs font-medium",
              isGood === false ? "text-ember" : "text-success",
            )}
          >
            {arrow} {Math.abs(delta!.value).toLocaleString()}
          </span>
        )}
      </div>
      {block.hint && <div className="mt-0.5 text-2xs text-text-muted">{block.hint}</div>}
    </div>
  );
}
