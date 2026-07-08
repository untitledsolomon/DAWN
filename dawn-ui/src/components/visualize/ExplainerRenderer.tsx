"use client";

import { useEffect, useRef, useState } from "react";
import { Play, Pause, RotateCcw, AlertCircle, Loader2, Maximize2, PlayIcon } from "lucide-react";

interface Props {
  code: string;
  title?: string;
  className?: string;
  compact?: boolean;
}

/**
 * ExplainerRenderer — renders a self-contained HTML/SVG/JS explainer fragment
 * inside a sandboxed iframe. Mirrors the ChartRenderer pattern for consistency.
 *
 * The iframe uses postMessage for a resize handshake so it auto-sizes to content.
 * Sandbox attributes prevent forms, popups, and top-navigation.
 */
export default function ExplainerRenderer({ code, title, className = "", compact = false }: Props) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [iframeHeight, setIframeHeight] = useState(compact ? 300 : 400);

  useEffect(() => {
    if (!iframeRef.current || !code) return;

    setLoading(true);
    setError(null);

    // Build the full HTML document from the fragment
    const fullHtml = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 100%; overflow-x: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
  body { padding: 0; }
  /* Respect reduced motion */
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
    }
  }
</style>
</head>
<body>
${code}
<script>
(function() {
  // Auto-resize: send height to parent on load and on resize
  function sendHeight() {
    const height = document.body.scrollHeight;
    window.parent.postMessage({ type: 'explainer-resize', height: height }, '*');
  }
  window.addEventListener('load', sendHeight);
  window.addEventListener('resize', sendHeight);
  // Also send after a short delay for async renders (KaTeX, etc.)
  setTimeout(sendHeight, 500);
  setTimeout(sendHeight, 1500);

  // Listen for play/pause/replay commands from parent
  window.addEventListener('message', function(event) {
    if (event.data && event.data.type === 'explainer-command') {
      const cmd = event.data.command;
      // Dispatch custom events on the document that the explainer's JS can listen for
      document.dispatchEvent(new CustomEvent('explainer-' + cmd));
    }
  });
})();
</script>
</body>
</html>`;

    const blob = new Blob([fullHtml], { type: "text/html" });
    const url = URL.createObjectURL(blob);

    const iframe = iframeRef.current;
    iframe.src = url;

    // Listen for resize messages from the iframe
    const handleMessage = (event: MessageEvent) => {
      if (
        event.data &&
        event.data.type === "explainer-resize" &&
        typeof event.data.height === "number"
      ) {
        setIframeHeight(Math.min(event.data.height + 20, 2000)); // cap at 2000px
        setLoading(false);
      }
    };

    window.addEventListener("message", handleMessage);

    // Fallback: if no resize message after 3s, show anyway
    const fallbackTimer = setTimeout(() => {
      setLoading(false);
    }, 3000);

    return () => {
      URL.revokeObjectURL(url);
      window.removeEventListener("message", handleMessage);
      clearTimeout(fallbackTimer);
    };
  }, [code]);

  const sendCommand = (command: "play" | "pause" | "replay") => {
    if (iframeRef.current?.contentWindow) {
      iframeRef.current.contentWindow.postMessage(
        { type: "explainer-command", command },
        "*"
      );
    }
  };

  return (
    <div className={`relative ${className}`}>
      {/* Header */}
      {title && (
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <PlayIcon size={14} className="text-dawn" />
            <span className="text-xs font-medium text-text-primary">{title}</span>
          </div>
          <div className="flex items-center gap-1">
            {/* Playback controls */}
            <button
              onClick={() => sendCommand("play")}
              className="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all"
              title="Play"
            >
              <Play size={11} />
            </button>
            <button
              onClick={() => sendCommand("pause")}
              className="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all"
              title="Pause"
            >
              <Pause size={11} />
            </button>
            <button
              onClick={() => sendCommand("replay")}
              className="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all"
              title="Replay"
            >
              <RotateCcw size={11} />
            </button>
            <button
              onClick={() => setExpanded(!expanded)}
              className="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all"
              title={expanded ? "Collapse" : "Expand"}
            >
              <Maximize2 size={11} />
            </button>
          </div>
        </div>
      )}

      {/* Explainer container */}
      <div
        ref={containerRef}
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

        <iframe
          ref={iframeRef}
          sandbox="allow-scripts allow-same-origin"
          className={`w-full border-0 ${loading || error ? "hidden" : ""}`}
          style={{
            height: expanded ? "100%" : `${iframeHeight}px`,
            maxWidth: "680px",
            margin: "0 auto",
            display: "block",
          }}
          title={title || "Explainer"}
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
