"use client";

import { useEffect, useState } from "react";

export interface CollectorStatus {
  connector_name: string;
  platform: string;
  status: string;
  data_status: string;
  data_access_status: string;
  last_successful_collection: string | null;
  retailer_requests: number;
  reason: string;
}

export function useCollectorStatus() {
  const [statuses, setStatuses] = useState<CollectorStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  useEffect(() => {
    let disposed = false;
    let active: AbortController | null = null;
    async function check() {
      if (active) return;
      const controller = new AbortController();
      active = controller;
      const timeout = window.setTimeout(() => controller.abort(), 8000);
      try {
        const base = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
        const response = await fetch(`${base}/collectors/status`, { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error("Status unavailable");
        const data = await response.json();
        if (!Array.isArray(data) || !data.every(item => item &&
          ["connector_name", "platform", "status", "data_status", "data_access_status", "reason"].every(key => typeof item[key] === "string") &&
          Number.isInteger(item.retailer_requests) && item.retailer_requests >= 0 &&
          (item.last_successful_collection === null || (typeof item.last_successful_collection === "string" && Number.isFinite(Date.parse(item.last_successful_collection)))))) throw new Error("Invalid status");
        if (!disposed) { setStatuses(data); setError(false); }
      } catch {
        if (!disposed) setError(true);
      } finally {
        window.clearTimeout(timeout);
        active = null;
        if (!disposed) setLoading(false);
      }
    }
    void check();
    const interval = window.setInterval(() => void check(), 10000);
    return () => { disposed = true; window.clearInterval(interval); active?.abort(); };
  }, []);
  return { statuses, loading, error };
}
