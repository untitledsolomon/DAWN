"use client";

import { Component, useState, type ReactNode } from "react";
import clsx from "clsx";
import type { Block, LeafBlock, UIDoc } from "@/lib/ui/schema";
import TextBlockBody from "./blocks/TextBlock";
import CalloutBlock from "./blocks/CalloutBlock";
import StatBlock from "./blocks/StatBlock";
import TableBlock from "./blocks/TableBlock";
import ChartBlock from "./blocks/ChartBlock";
import KeyValueBlock from "./blocks/KeyValueBlock";
import CodeBlock from "./blocks/CodeBlock";
import TimelineBlock from "./blocks/TimelineBlock";
import ButtonBlock from "./blocks/ButtonBlock";

// One bad block renders a small inline note, never a blank message.
class BlockBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className="px-3 py-2 rounded-[8px] border border-rim bg-elevated/40 text-text-muted text-2xs">
        Couldn&apos;t render this block.
      </div>
    ) : (
      this.props.children
    );
  }
}

function LeafRenderer({ block }: { block: LeafBlock }) {
  switch (block.type) {
    case "text":
      return <TextBlockBody block={block} />;
    case "callout":
      return <CalloutBlock block={block} />;
    case "stat":
      return <StatBlock block={block} />;
    case "table":
      return <TableBlock block={block} />;
    case "chart":
      return <ChartBlock block={block} />;
    case "key_value":
      return <KeyValueBlock block={block} />;
    case "code":
      return <CodeBlock block={block} />;
    case "timeline":
      return <TimelineBlock block={block} />;
    case "button":
      return <ButtonBlock block={block} />;
    default:
      return null;
  }
}

function BlockRenderer({ block }: { block: Block }) {
  if (block.type === "columns") {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {block.children.map((child, i) => (
          <BlockBoundary key={child.id ?? `c${i}`}>
            <LeafRenderer block={child} />
          </BlockBoundary>
        ))}
      </div>
    );
  }
  if (block.type === "tabs") {
    return (
      <TabsRenderer
        tabs={block.tabs.map((t) => ({
          label: t.label,
          node: (
            <div className="space-y-3">
              {t.children.map((child, i) => (
                <BlockBoundary key={child.id ?? `t${i}`}>
                  <LeafRenderer block={child} />
                </BlockBoundary>
              ))}
            </div>
          ),
        }))}
      />
    );
  }
  return <LeafRenderer block={block} />;
}

function TabsRenderer({ tabs }: { tabs: { label: string; node: ReactNode }[] }) {
  const [active, setActive] = useState(0);
  const safe = Math.min(active, tabs.length - 1);
  return (
    <div className="border border-rim rounded-[10px] overflow-hidden">
      <div className="flex border-b border-rim bg-elevated/40 overflow-x-auto">
        {tabs.map((t, i) => (
          <button
            key={t.label}
            onClick={() => setActive(i)}
            className={clsx(
              "px-3 py-1.5 text-xs font-medium whitespace-nowrap border-r border-rim transition-colors",
              i === safe
                ? "bg-surface text-dawn"
                : "text-text-muted hover:text-text-secondary"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="p-3">{tabs[safe]?.node}</div>
    </div>
  );
}

export default function UIRenderer({
  doc,
  className,
}: {
  doc: UIDoc;
  className?: string;
}) {
  return (
    <div className={className}>
      {doc.title ? (
        <div className="text-sm font-semibold text-text-primary mb-2">{doc.title}</div>
      ) : null}
      <div className="space-y-3">
        {(doc.blocks ?? []).map((block, i) => (
          <BlockBoundary key={block.id ?? `b${i}`}>
            <BlockRenderer block={block} />
          </BlockBoundary>
        ))}
      </div>
      {doc._meta && doc._meta.dropped > 0 ? (
        <p className="text-text-muted text-2xs mt-2">
          {doc._meta.dropped} block(s) couldn&apos;t be rendered.
        </p>
      ) : null}
    </div>
  );
}
