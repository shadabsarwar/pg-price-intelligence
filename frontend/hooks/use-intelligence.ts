 "use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { isCompetitorComparison, type CompetitorComparison } from "@/types/intelligence";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export function useIntelligence(productId: number) {
  const [data, setData] = useState<CompetitorComparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const active = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setRefreshing(true);
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(`${API_URL}/products/${productId}/competitor-comparison`, { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error(response.status === 404 ? "This master product no longer exists." : `API returned HTTP ${response.status}.`);
      const payload = await response.json();
      if (!isCompetitorComparison(payload)) throw new Error("Unexpected intelligence response.");
      if (active.current !== controller) return;
      setData(payload);
      setError(null);
      setUpdatedAt(Date.now());
    } catch (failure) {
      if (active.current === controller) setError(failure instanceof Error && failure.name !== "AbortError" ? failure.message : "API request timed out.");
    } finally {
      window.clearTimeout(timeout);
      if (active.current === controller) {
        active.current = null;
        setRefreshing(false);
      }
    }
  }, [productId]);
  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    const interval = window.setInterval(() => void refresh(), 10000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(interval);
      const controller = active.current;
      active.current = null;
      controller?.abort();
    };
  }, [refresh]);
  return { data, error, refreshing, updatedAt, refresh };
}
