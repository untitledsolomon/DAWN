"use client";

import { createContext, useContext, type ReactNode } from "react";
import { useRouter } from "next/navigation";

// Actions on ui blocks. `prompt` sends a follow-up through the normal agent
// path; `navigate` goes to an internal page; `tool` (Phase 4) runs a
// server-side allowlisted tool. The provider wires these to real functions;
// the default dispatches `dawn:ui-prompt` so any listen host can send it.
export interface ActionContextValue {
  sendPrompt: (text: string) => void;
  navigate: (to: string) => void;
  runToolAction: (action: { tool: string; args?: Record<string, unknown>; inputs?: string[] }) => void;
}

const defaultContext: ActionContextValue = {
  sendPrompt: (text) => {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("dawn:ui-prompt", { detail: { text } }));
    }
  },
  navigate: () => {},
  runToolAction: () => {},
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
    runToolAction: () => {},
    ...value,
  };
  return <ActionContext.Provider value={ctx}>{children}</ActionContext.Provider>;
}
