import type { Product } from "@/types/product";

export function compareProduct(product: Product) {
  const listings = product.listings ?? [];
  const sameCurrency = listings.filter(item => item.currency === product.currency);
  const source = sameCurrency.some(item => item.data_source === "verified") ? "verified" : "demo";
  const eligible = sameCurrency.filter(item => item.availability === "available" && item.data_source === source && item.data_status !== "STALE" && item.data_status !== "ERROR");
  return {
    listings, eligible, source,
    lowest: eligible.length ? Math.min(...eligible.map(item => item.price)) : null,
    highest: eligible.length ? Math.max(...eligible.map(item => item.price)) : null,
    platforms: new Set(listings.map(item => item.platform)).size,
    updatedAt: listings.length ? Math.max(...listings.map(item => Date.parse(item.last_updated))) : null,
  };
}

export function safeImageUrl(url?: string | null) {
  return url && (/^https?:\/\//i.test(url) || /^\/(?!\/)/.test(url)) ? url : undefined;
}

export function relativeTime(timestamp: number | null, now: number) {
  if (timestamp === null) return "Not yet collected";
  const seconds = Math.max(0, Math.floor((now - timestamp) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`;
  return `${Math.floor(seconds / 86400)} days ago`;
}
