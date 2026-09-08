"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { isProduct, type Product } from "@/types/product";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export function useProducts() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [now, setNow] = useState(0);
  const active = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setRefreshing(true);
    const timeout = window.setTimeout(() => controller.abort(), 30000);
    try {
      const data: Product[] = [];
      for (let offset = 0; ; offset += 500) {
        const response = await fetch(`${API_URL.replace(/\/$/, "")}/products?limit=500&offset=${offset}`, {
          cache: "no-store", signal: controller.signal,
        });
        if (!response.ok) throw new Error(`API returned HTTP ${response.status}.`);
        const page: unknown = await response.json();
        if (!Array.isArray(page) || !page.every(isProduct)) throw new Error("The API returned an unexpected product format.");
        data.push(...page);
        if (page.length < 500) break;
      }
      if (active.current !== controller) return;
      setProducts(data);
      setUpdatedAt(Date.now());
      setNow(Date.now());
      setError(null);
    } catch (failure) {
      if (active.current !== controller) return;
      setError(failure instanceof Error && failure.name !== "AbortError"
        ? failure.message : "The API took too long to respond.");
    } finally {
      window.clearTimeout(timeout);
      if (active.current === controller) {
        active.current = null;
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    const poll = window.setInterval(() => void refresh(), 10_000);
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(poll);
      window.clearInterval(clock);
      const controller = active.current;
      active.current = null;
      controller?.abort();
    };
  }, [refresh]);

  const secondsAgo = updatedAt ? Math.max(0, Math.floor((now - updatedAt) / 1000)) : null;
  const live = updatedAt !== null && !error && secondsAgo !== null && secondsAgo < 25;
  const updatedLabel = secondsAgo === null ? "Waiting for first update"
    : secondsAgo < 2 ? "Updated just now" : `Last updated ${secondsAgo} seconds ago`;
  return { products, loading, refreshing, error, updatedAt, updatedLabel, live, refresh, now };
}
