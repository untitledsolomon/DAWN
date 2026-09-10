"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";

/**
 * /visualize has been unified into /canvas (Canvas now includes the live
 * streaming chat that VisualizeWindow used to provide). Redirect to /canvas,
 * preserving any session id so existing bookmarked/shared links still resolve.
 */
export default function VisualizePage() {
  const searchParams = useSearchParams();
  const id = searchParams.get("id");

  useEffect(() => {
    const target = id ? `/canvas?id=${encodeURIComponent(id)}` : "/canvas";
    window.location.replace(target);
  }, [id]);

  return null;
}
