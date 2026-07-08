"use client";

import { useEffect, useRef, useState } from "react";
import { BarChart3, Loader2, AlertCircle, Maximize2, Download } from "lucide-react";

interface Props {
  spec: Record<string, unknown>;
  title?: string;
  className?: string;
  compact?: boolean;
}

export default function ChartRenderer({ spec, title, className = "", compact = false }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!ref.current || !spec) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    // Dynamic import of vega-embed (it's large, so lazy load at runtime only)
    import("vega-embed")
      .then((mod) => {
        if (cancelled) return;
        const embed = mod.default;

        embed(ref.current!, spec as any, {
          actions: {
            export: true,
            source: false,
            compiled: false,
            editor: false,
          },
          renderer: "canvas",
          tooltip: true,
          width: compact ? 280 : undefined,
          height: compact ? 200 : undefined,
          padding: { left: 5, right: 5, top: 5, bottom: 5 },
        })
          .then(() => {
            if (!cancelled) setLoading(false);
          })
          .catch((err) => {
            if (!cancelled) {
              console.error("[ChartRenderer] Vega-embed error:", err);
              setError(err.message || "Failed to render chart");
              setLoading(false);
            }
          });
      })
      .catch((err) => {
        if (!cancelled) {
          console.error("[ChartRenderer] Failed to load vega-embed:", err);
          setError("Failed to load chart library");
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [spec, compact]);

  const handleDownload = async () => {
    if (!ref.current) return;
    const canvas = ref.current.querySelector("canvas");
    if (canvas) {
      const link = document.createElement("a");
      link.download = `${title || "chart"}.png`;
      link.href = canvas.toDataURL("image/png");
      link.click();
    }
  };

  return (
    <div className={`relative ${className}`}>
      {/* Header */}
      {title && (
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <BarChart3 size={14} className="text-dawn" />
            <span className="text-xs font-medium text-text-primary">{title}</span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setExpanded(!expanded)}
              className="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all"
              title={expanded ? "Collapse" : "Expand"}
            >
              <Maximize2 size={11} />
            </button>
            <button
              onClick={handleDownload}
              className="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all"
              title="Download PNG"
            >
              <Download size={11} />
            </button>
          </div>
        </div>
      )}

      {/* Chart container */}
      <div
        className={`relative rounded-xl border border-rim bg-surface/50 overflow-hidden transition-all ${
          expanded ? "fixed inset-4 z-50 flex items-center justify-center bg-abyss/90" : ""
        }`}
      >
        {loading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={20} className="text-dawn animate-spin" />
          </div>
        )}

        {error && (
          <div className="flex flex-col items-center justify-center py-8 gap-2">
            <AlertCircle size={18} className="text-ember" />
            <p className="text-text-muted text-xs">{error}</p>
          </div>
        )}

        <div
          ref={ref}
          className={`flex items-center justify-center ${loading || error ? "hidden" : ""}`}
          style={{ minHeight: compact ? 180 : 300 }}
        />

        {/* Close button for expanded mode */}
        {expanded && (
          <button
            onClick={() => setExpanded(false)}
            className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-lg bg-surface border border-rim text-text-primary hover:text-dawn transition-all"
          >
            <span className="text-sm font-medium">✕</span>
          </button>
        )}
      </div>
    </div>
  );
}
