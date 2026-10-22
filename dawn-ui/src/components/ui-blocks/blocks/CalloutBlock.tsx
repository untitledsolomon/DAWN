import clsx from "clsx";
import type { CalloutBlock as CalloutBlockT } from "@/lib/ui/schema";

const TONES = {
  info: "border-rim bg-elevated/40 text-text-secondary",
  warn: "border-amber/40 bg-amber/5 text-text-primary",
  danger: "border-ember/40 bg-ember/5 text-text-primary",
  success: "border-success/40 bg-success/5 text-text-primary",
} as const;

export default function CalloutBlock({ block }: { block: CalloutBlockT }) {
  return (
    <div
      className={clsx(
        "px-3 py-2 rounded-[8px] border",
        TONES[block.tone ?? "info"],
      )}
    >
      {block.title && (
        <div className="text-xs font-semibold text-text-primary mb-0.5">{block.title}</div>
      )}
      <div className="text-xs leading-relaxed">{block.text}</div>
    </div>
  );
}
