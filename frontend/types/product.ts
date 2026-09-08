export type DataStatus = "LIVE" | "VERIFIED" | "STALE" | "DEMO" | "ERROR" | "IMPORTED" | "MANUAL" | "COLLECTED" | "UNAVAILABLE";

export interface PlatformListing {
  platform: string;
  platform_product_id: string;
  product_name: string;
  price: number;
  original_price: number | null;
  currency: string;
  product_url: string | null;
  image_url: string | null;
  availability: "available" | "out_of_stock" | "unknown";
  last_updated: string;
  data_source: "demo" | "verified";
  data_status?: DataStatus;
  source_name?: string;
}

export interface Product {
  id: number;
  company: string;
  brand: string;
  product_name: string;
  category: string;
  size: string;
  barcode: string;
  price: number | null;
  currency: string;
  image_url?: string | null;
  listings?: PlatformListing[];
  data_status?: DataStatus;
  subcategory?: string | null;
  purpose?: string | null;
  variant?: string | null;
  size_value?: number | null;
  unit?: string | null;
  pack_quantity?: number | null;
  attributes?: Record<string, string>;
  source_state?: DataStatus;
  quality_flags?: string[];
  verified?: boolean;
  product_family?: string | null;
}

export function isProduct(value: unknown): value is Product {
  if (typeof value !== "object" || value === null) return false;
  const p = value as Record<string, unknown>;
  return Number.isInteger(p.id) && (p.price === null || (typeof p.price === "number" && Number.isFinite(p.price)))
    && ["company", "brand", "product_name", "category", "size", "barcode", "currency"].every(key => typeof p[key] === "string")
    && (p.image_url == null || typeof p.image_url === "string")
    && (p.listings === undefined || (Array.isArray(p.listings) && p.listings.every(isListing)));
}

function isListing(value: unknown): value is PlatformListing {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return ["platform", "platform_product_id", "product_name", "currency", "last_updated"].every(key => typeof item[key] === "string")
    && typeof item.price === "number" && Number.isFinite(item.price) && item.price >= 0
    && (item.original_price === null || (typeof item.original_price === "number" && Number.isFinite(item.original_price)))
    && ["image_url", "product_url"].every(key => item[key] === null || typeof item[key] === "string")
    && ["available", "out_of_stock", "unknown"].includes(String(item.availability))
    && ["demo", "verified"].includes(String(item.data_source))
    && Number.isFinite(Date.parse(String(item.last_updated)));
}
