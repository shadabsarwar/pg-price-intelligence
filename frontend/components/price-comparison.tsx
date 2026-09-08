"use client";

import { useEffect, useRef } from "react";
import type { Product } from "@/types/product";
import { compareProduct, relativeTime } from "@/lib/comparison";
import { ProductImage } from "./product-image";
import { DataStatusBadge } from "./data-status";
import { RetailerAvailability } from "./retailer-availability";
import { LiveComparison } from "./live-comparison";
import { PriceHistory } from "./price-history";

export function PriceComparison({ product, now, live, refreshing, updatedLabel, onClose }: {
  product: Product; now: number; live: boolean; refreshing: boolean; updatedLabel: string; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const comparison = compareProduct(product);

  useEffect(() => {
    const element = dialog.current;
    const previousFocus = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    element?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      element?.close();
      document.body.style.overflow = overflow;
      previousFocus?.focus();
    };
  }, []);

  return <dialog ref={dialog} onCancel={event => { event.preventDefault(); onClose(); }} aria-labelledby="comparison-title" className="fixed inset-0 m-auto max-h-[90dvh] w-[calc(100%-2rem)] max-w-6xl overflow-y-auto rounded-2xl border border-slate-200 bg-white p-0 text-slate-900 shadow-2xl backdrop:bg-slate-950/60">
    <div className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-slate-200 bg-white px-5 py-4"><div><p className="text-[10px] font-bold uppercase tracking-widest text-blue-700">Platform comparison</p><h2 id="comparison-title" className="mt-1 text-lg font-semibold">Compare Prices</h2></div><button onClick={onClose} autoFocus aria-label="Close price comparison" className="rounded-lg border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50">Close ×</button></div>
    <div className="p-5 sm:p-7">
      <LiveComparison key={product.id} productId={product.id} />
      <PriceHistory key={`history-${product.id}`} productId={product.id} />
      <RetailerAvailability platforms={[...new Set(comparison.listings.map(item => item.platform))]} />
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center"><div className="h-36 w-36 shrink-0"><ProductImage url={product.image_url} name={product.product_name} brand={product.brand} /></div><div><p className="text-xs font-bold uppercase tracking-widest text-blue-700">{product.brand}</p><h3 className="mt-2 text-2xl font-semibold">{product.product_name}</h3><p className="mt-2 text-sm text-slate-500">{product.company} · {product.category} · {product.size}</p><p className="mt-3 text-xs text-slate-500">{comparison.platforms} platforms · {refreshing ? "Refreshing API…" : live ? "API connected" : "API offline — data may be stale"} · {updatedLabel}</p></div></div>
      {comparison.listings.some(item => item.data_source === "demo") && <p className="mt-5 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Development data: demo prices, availability, IDs and timestamps are synthetic. Retailer names illustrate the comparison; these are not live market offers.</p>}
      <div className="my-6 grid gap-3 sm:grid-cols-3">
        <Metric label="Lowest price / Best deal" value={comparison.lowest === null ? "No available offer" : `${comparison.lowest.toFixed(2)} ${product.currency}`} accent />
        <Metric label="Highest comparable price" value={comparison.highest === null ? "—" : `${comparison.highest.toFixed(2)} ${product.currency}`} />
        <Metric label="Latest listing update" value={relativeTime(comparison.updatedAt, now)} />
      </div>
      <p className="mb-3 text-xs leading-5 text-slate-500">Price highlights use available {comparison.source} listings in {product.currency} only. Best deal means lowest listed price, before delivery or other fees. Verified and demo offers are never ranked together.</p>
      {comparison.listings.length === 0 ? <p className="rounded-xl border border-dashed border-slate-300 p-10 text-center text-slate-500">No platform listings have been collected for this product yet.</p> : <div className="overflow-x-auto rounded-xl border border-slate-200" tabIndex={0} role="region" aria-label="Platform price comparison table, scroll horizontally on small screens">
        <table className="w-full min-w-[950px] text-left text-sm"><caption className="sr-only">Platform prices for {product.product_name}</caption><thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Platform", "Product Image", "Current Price", "Original Price", "Availability", "Last Updated", "Product Link"].map(label => <th key={label} scope="col" className="px-4 py-3 font-medium">{label}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">{comparison.listings.map(item => {
            const eligible = comparison.eligible.includes(item);
            const lowest = eligible && item.price === comparison.lowest;
            const highest = eligible && item.price === comparison.highest;
            const link = item.product_url && /^https?:\/\//i.test(item.product_url) ? item.product_url : null;
            return <tr key={`${item.platform}-${item.platform_product_id}`} className={lowest ? "bg-emerald-50/60" : "bg-white"}>
              <th scope="row" className="px-4 py-4 font-medium"><span>{item.platform}</span><span className={`mt-1 block text-[10px] uppercase tracking-wide ${item.data_source === "demo" ? "text-amber-700" : "text-emerald-700"}`}><DataStatusBadge status={item.data_status ?? (item.data_source === "demo" ? "DEMO" : "VERIFIED")} /></span><span className="mt-1 block text-[10px] font-normal text-slate-400">{item.platform_product_id}</span><span className="mt-1 block text-[10px] font-normal text-slate-500">{item.source_name ?? item.data_source}</span></th>
              <td className="px-4 py-3"><div className="h-16 w-16"><ProductImage url={item.image_url} name={item.product_name} brand={product.brand} compact /></div></td>
              <td className="px-4 py-3"><span className="whitespace-nowrap font-semibold">{item.price.toFixed(2)} {item.currency}</span>{lowest && <span className="mt-1 block text-[10px] font-semibold text-emerald-700">Lowest · Best deal</span>}{highest && <span className="mt-1 block text-[10px] text-slate-500">Highest{lowest ? " (tied)" : ""}</span>}</td>
              <td className="whitespace-nowrap px-4 py-3 text-slate-500">{item.original_price === null ? "—" : <span className={item.original_price > item.price ? "line-through" : ""}>{item.original_price.toFixed(2)} {item.currency}</span>}</td>
              <td className="px-4 py-3"><span className={item.availability === "available" ? "text-emerald-700" : "text-slate-500"}>{item.availability === "available" ? "Available" : item.availability === "out_of_stock" ? "Out of stock" : "Unknown"}</span></td>
              <td className="px-4 py-3 text-xs text-slate-500"><time dateTime={item.last_updated} title={new Date(item.last_updated).toLocaleString()}>{relativeTime(Date.parse(item.last_updated), now)}</time></td>
              <td className="px-4 py-3">{link ? <a href={link} target="_blank" rel="noopener noreferrer" className="font-medium text-blue-700 underline underline-offset-4" aria-label={`View product at ${item.platform}`}>View Product ↗</a> : <span className="text-xs text-slate-400">{item.data_source === "demo" ? "No demo product link" : "Link not supplied"}</span>}</td>
            </tr>;
          })}</tbody>
        </table>
      </div>}
    </div>
  </dialog>;
}

function Metric({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return <div className={`rounded-xl border p-4 ${accent ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-slate-50"}`}><p className="text-xs text-slate-500">{label}</p><p className={`mt-2 text-lg font-semibold ${accent ? "text-emerald-800" : "text-slate-900"}`}>{value}</p></div>;
}

