import type { KeyValueBlock as KeyValueBlockT } from "@/lib/ui/schema";

export default function KeyValueBlock({ block }: { block: KeyValueBlockT }) {
  return (
    <dl className="divide-y divide-rim border border-rim rounded-[8px] overflow-hidden">
      {(block.items ?? []).map((item, i) => (
        <div key={i} className="flex items-baseline justify-between gap-4 px-3 py-2">
          <dt className="text-xs text-text-muted">{item.label}</dt>
          <dd className="text-xs font-medium text-text-primary text-right">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
