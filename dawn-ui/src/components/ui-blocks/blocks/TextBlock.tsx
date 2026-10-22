import type { TextBlock as TextBlockT } from "@/lib/ui/schema";
import { renderMarkdown } from "@/lib/ui/markdown";

export default function TextBlock({ block }: { block: TextBlockT }) {
  return (
    <div className="text-sm leading-relaxed text-text-primary dawn-prose">
      {renderMarkdown(block.markdown)}
    </div>
  );
}
