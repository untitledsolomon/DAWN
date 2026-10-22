"use client";

import { useEffect, useRef } from "react";
import katex from "katex";

// KaTeX wrapper with the fixed options the learning spec demands: trust:false
// (blocks \href/\url/\includegraphics), throwOnError:false (bad LaTeX renders
// in the ember colour, never blanks a message). errorColor maps to the app's
// ember token (#B84D3B, tailwind.config.ts).
const KATEX_OPTIONS = {
  throwOnError: false,
  errorColor: "#B84D3B", // ember token (tailwind.config.ts)
  trust: false,
  strict: "ignore",
  maxExpand: 200,
  maxSize: 20,
  output: "htmlAndMathml",
} as const;

const MAX_TEX = 2000;

export default function Math({ tex, display = true }: { tex: string; display?: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (tex.length > MAX_TEX) {
      el.textContent = tex;
      return;
    }
    try {
      katex.render(tex, el, { ...KATEX_OPTIONS, displayMode: display });
    } catch {
      el.textContent = tex; // never blank the message
    }
  }, [tex, display]);

  return <span ref={ref} />;
}
