"use client";

import { createContext, useContext, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import type { Action } from "@/lib/ui/schema";

// Actions on ui blocks. `prompt` sends a follow-up through the normal agent
// path; `navigate` goes to an internal page; `tool` runs a server-side
// allowlisted tool (see routers/agent.py /agent/ui-action). The default
// dispatches `dawn:ui-prompt` for prompts; `runToolAction` is wired per
// artifact by ArtifactBody (which knows the stored artifact id).
export interface ActionContextValue {
  sendPrompt: (text: string) => void;
  navigate: (to: string) => void;
  runToolAction: (
    action: Action,
    blockId: string,
    inputs?: Record<string, unknown>,
  ) => Promise<{ status: string; action_id?: string } | void>;
}

const defaultContext: ActionContextValue = {
  sendPrompt: (text) => {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("dawn:ui-prompt", { detail: { text } }));
    }
  },
  navigate: () => {},
  runToolAction: async () => undefined,
};

export const ActionContext = createContext<ActionContextValue>(defaultContext);

export function useActions(): ActionContextValue {
  return useContext(ActionContext);
}

export function ActionContextProvider({
  value,
  children,
}: {
  value?: Partial<ActionContextValue>;
  children: ReactNode;
}) {
  const router = useRouter();
  const ctx: ActionContextValue = {
    sendPrompt: defaultContext.sendPrompt,
    navigate: (to) => {
      if (to && to.startsWith("/")) router.push(to);
    },
    runToolAction: async () => undefined,
    ...value,
  };
  return <ActionContext.Provider value={ctx}>{children}</ActionContext.Provider>;
}
