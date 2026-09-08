"use client";

import type { Product } from "@/types/product";
import { compareProduct, relativeTime } from "@/lib/comparison";
import { DashboardIcon, LiveBadge } from "./dashboard-icon";
import { ProductImage } from "./product-image";
import { DataStatusBadge } from "./data-status";

export function ProductCard({ product, live, updatedLabel, now, onCompare, onCompetitors }: {
  product: Product; live: boolean; updatedLabel: string; now: number; onCompare: () => void; onCompetitors: () => void;
}) {
  const comparison = compareProduct(product);
  const hasDemo = comparison.listings.some(item => item.data_source === "demo");
  return <article className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
    <div className="relative h-56 bg-slate-50 p-4">
      <ProductImage url={product.image_url} name={product.product_name} brand={product.brand} />
      <span className="absolute left-4 top-4 rounded-md border border-slate-200 bg-white/95 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest text-slate-600">{product.category}</span>
    </div>
    <div className="p-5 sm:p-6">
      <div className="flex items-center justify-between gap-3"><span className="text-xs font-bold uppercase tracking-[0.15em] text-blue-700">{product.brand}</span><LiveBadge live={live} label={live ? "API connected" : "API offline"} /></div>
      <h3 className="mt-3 min-h-14 break-words text-lg font-semibold leading-7 text-slate-900"><button onClick={onCompetitors} className="text-left hover:text-blue-700">{product.product_name}</button></h3>
      <p className="mt-1 text-sm text-slate-500">{product.company}</p>
      <div className="mt-2"><DataStatusBadge status={product.data_status ?? (hasDemo ? "DEMO" : "ERROR")} /></div>
      <p className="mt-2 text-xs text-slate-500">Source: {product.source_state ?? "Unknown"}{product.verified ? " · Identity verified" : ""}</p>
      {!!product.quality_flags?.length && <p className="mt-2 text-xs text-amber-800">{product.quality_flags.map(flag => flag.replaceAll("_", " ").toLowerCase()).join(" · ")}</p>}
      <p className="mt-5 text-xs font-medium text-slate-500">{comparison.lowest === null ? "No comparable available offers" : comparison.source === "demo" ? "Best demo price" : "Best recorded available price"}</p>
      <div className="mt-1 flex items-baseline gap-2"><span className="text-3xl font-semibold tracking-tight text-slate-900">{comparison.lowest?.toFixed(2) ?? "—"}</span><span className="text-sm font-semibold text-slate-500">{product.currency}</span></div>
      <p className="mt-2 text-xs text-slate-500">{comparison.platforms} platforms {hasDemo ? "· Includes demo listings" : comparison.platforms ? "· See each offer's source" : "· No listings yet"}</p>
      <dl className="mt-5 grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 text-sm"><div><dt className="text-xs text-slate-500">Size</dt><dd className="mt-1 font-medium">{product.size}</dd></div><div className="text-right"><dt className="text-xs text-slate-500">Product ID</dt><dd className="mt-1 font-mono">#{String(product.id).padStart(3, "0")}</dd></div></dl>
      <p className="mt-4 text-[11px] text-slate-500">Listing update: {relativeTime(comparison.updatedAt, now)}</p>
      <p className="mt-1 text-[11px] text-slate-400" title="Last successful API refresh">API: {updatedLabel}</p>
      <button onClick={onCompare} className="mt-5 flex w-full items-center justify-center gap-2 rounded-lg bg-blue-800 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-900">Compare Prices<DashboardIcon name="arrow" className="h-4 w-4" /></button>
      <button onClick={onCompetitors} className="mt-3 w-full rounded-lg border border-blue-800 px-4 py-3 text-sm font-semibold text-blue-800 hover:bg-blue-50">Compare Competitors</button>
    </div>
  </article>;
}
