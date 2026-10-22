"use client";

import { useState } from "react";
import { Copy, Check } from "lucide-react";
import type { CodeBlock as CodeBlockT } from "@/lib/ui/schema";

export default function CodeBlock({ block }: { block: CodeBlockT }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(block.text ?? "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard unavailable — ignore
    }
  };
  return (
    <div className="rounded-[8px] border border-rim overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 bg-elevated/50 border-b border-rim">
        <span className="text-2xs font-mono text-text-muted uppercase tracking-wider">
          {block.language || "code"}
        </span>
        <button
          onClick={copy}
          className="flex items-center gap-1 text-text-muted hover:text-text-secondary text-2xs"
          title="Copy"
        >
          {copied ? <Check size={11} className="text-success" /> : <Copy size={11} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="px-3 py-2 overflow-x-auto text-xs font-mono text-text-secondary leading-relaxed">
        {block.text}
      </pre>
    </div>
  );
}
