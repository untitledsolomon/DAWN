"use client";

import clsx from "clsx";

/**
 * Shared pill token — one consistent visual treatment for small category /
 * impact / sandbox labels across the app (Canvas "Sandboxed" badge, Approvals
 * category tags and impact indicators). Casing is uppercase mono by default to
 * match the preview's `.tag` / `.sandbox` treatment.
 */
type Tone = "neutral" | "teal" | "amber";

const TONES: Record<Tone, string> = {
  neutral: "bg-elevated border-rim text-text-muted",
  teal: "bg-dawn/10 border-dawn/20 text-dawn",
  amber: "bg-amber/10 border-amber/25 text-amber",
};

interface Props {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}

export default function Pill({ children, tone = "neutral", className }: Props) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full border px-1.5 py-0.5 font-mono text-2xs uppercase tracking-wider",
        TONES[tone],
        className
      )}
    >
      {children}
    </span>
  );
}
