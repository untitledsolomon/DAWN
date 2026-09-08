"use client";

import { useEffect, useState, useCallback } from "react";
import { AlertTriangle, AlertOctagon, Info, X } from "lucide-react";
import clsx from "clsx";
import { listAlertEvents, acknowledgeAlert } from "@/lib/api";
import type { AlertEvent } from "@/lib/types";
import { timeAgo } from "@/lib/format";

const SEVERITY_STYLE: Record<string, { border: string; icon: React.ElementType; iconColor: string }> = {
  critical: { border: "border-l-ember", icon: AlertOctagon, iconColor: "text-ember" },
  warning: { border: "border-l-amber", icon: AlertTriangle, iconColor: "text-amber" },
  info: { border: "border-l-text-muted", icon: Info, iconColor: "text-text-muted" },
};

/**
 * Reframes raw monitoring alert copy into DAWN's first-person voice where the
 * underlying message allows it. Falls back to the original title otherwise.
 */
function reframe(alert: AlertEvent): string {
  const msg = alert.message?.trim();
  if (msg) {
    const lower = msg.toLowerCase();
    if (!/^(i|we|dawn|the system|monitoring)/.test(lower)) {
      return `I'm seeing ${msg.charAt(0).toLowerCase()}${msg.slice(1)}`;
    }
    return msg;
  }
  const t = alert.title?.trim();
  if (t) {
    const lower = t.toLowerCase();
    if (!/^(i|we|dawn|the system|monitoring)/.test(lower)) {
      return `I'm seeing ${t.charAt(0).toLowerCase()}${t.slice(1)}`;
    }
    return t;
  }
  return "I'm watching this.";
}

export default function AlertStrip() {
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await listAlertEvents(20);
      setAlerts(data);
    } catch (err) {
      console.error("[AlertStrip] Failed to load alerts:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleAck = async (id: string) => {
    try {
      await acknowledgeAlert(id);
      setAlerts((prev) => prev.filter((a) => a.id !== id));
    } catch (err) {
      console.error("[AlertStrip] Failed to acknowledge:", err);
    }
  };

  const style = (sev: string) => SEVERITY_STYLE[sev] || SEVERITY_STYLE.info;
  const visible = alerts.filter((a) => !a.acknowledged);

  return (
    <section className="card overflow-hidden">
      <div className="cardhead">
        <div>
          <p className="eyebrow">Attention</p>
          <h2 className="text-[13px] font-semibold text-text-primary">What I&apos;m watching</h2>
        </div>
        <span className="mono">{visible.length} recent</span>
      </div>
      <div className="alerts">
        {loading ? (
          <div className="px-4 py-6 text-center text-text-muted text-xs">Loading alerts…</div>
        ) : visible.length === 0 ? (
          <div className="px-4 py-6 text-center text-text-muted text-xs">
            Nothing needs my attention right now.
          </div>
        ) : (
          visible.map((alert) => {
            const s = style(alert.severity);
            const Icon = s.icon;
            return (
              <div
                key={alert.id}
                className={clsx("alert", s.border)}
              >
                <Icon size={13} className={clsx("alert-icon", s.iconColor)} />
                <div className="alert-main">
                  <b className="text-[12px] font-medium text-text-primary">{reframe(alert)}</b>
                  {alert.message && (
                    <small className="block text-text-muted text-[10px] mt-0.5">{alert.title}</small>
                  )}
                </div>
                <span className="mono">{timeAgo(alert.created_at)}</span>
                <button
                  onClick={() => handleAck(alert.id)}
                  className="ack"
                  title="Acknowledge"
                >
                  <X size={11} />
                </button>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
