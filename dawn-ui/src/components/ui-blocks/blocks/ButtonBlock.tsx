"use client";

import clsx from "clsx";
import type { ButtonBlock as ButtonBlockT } from "@/lib/ui/schema";
import { useActions } from "../ActionContext";

export default function ButtonBlock({ block }: { block: ButtonBlockT }) {
  const { sendPrompt, navigate, runToolAction } = useActions();
  const action = block.action;

  const onClick = () => {
    if (!action) return;
    if (action.kind === "prompt" && action.text) {
      sendPrompt(action.text);
    } else if (action.kind === "navigate" && action.to) {
      navigate(action.to);
    } else if (action.kind === "tool" && action.tool) {
      // Confirm is built from the stored spec (tool name + args), never from
      // the model-supplied label.
      const argsSummary = Object.entries(action.args ?? {})
        .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
        .join(", ");
      const msg = `Run tool '${action.tool}'${argsSummary ? ` with: ${argsSummary}` : "?"}`;
      if (window.confirm(`${msg}`)) {
        void runToolAction(action, block.id ?? "");
      }
    }
  };

  return (
    <button
      onClick={onClick}
      className={clsx(
        "px-3 py-1.5 rounded-[8px] text-xs font-medium border transition-all",
        block.variant === "primary"
          ? "bg-dawn/90 text-white border-dawn/90 hover:bg-dawn"
          : "bg-surface text-text-secondary border-rim hover:border-dawn/40 hover:text-text-primary",
      )}
    >
      {block.label}
    </button>
  );
}
