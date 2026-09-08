"use client";

import { useEffect, useState } from "react";
import { DataStatusBadge } from "./data-status";
import { ProductImage } from "./product-image";

type Offer = {
  platform: string; company: string; brand: string; product_name: string;
  product_image: string | null; product_url: string | null;
  current_price: number | null; currency: string; price_per_unit: number | null;
  normalized_unit: string | null; availability: string; collected_at: string;
  data_status: "LIVE" | "STALE";
};
type Comparison = {
  product_id: number; data_status: "LIVE" | "STALE" | "UNAVAILABLE"; reason: string | null;
  pg_product: { product_name: string; offers: Offer[] }; competitor_products: Offer[];
  sources: { platform: string; data_status: "LIVE" | "STALE" | "UNAVAILABLE"; reason: string | null }[];
};
const api = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const money = (value: number | null, currency: string) => value === null ? "Unavailable" : `${value.toFixed(2)} ${currency}`;

export function LiveComparison({ productId }: { productId: number }) {
  const [data, setData] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 12000);
    fetch(`${api}/products/${productId}/live-comparison`, { cache: "no-store", signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error("Live comparison is unavailable."); return response.json(); })
      .then((result: Comparison) => {
        if (result.product_id !== productId || !Array.isArray(result.pg_product?.offers) || !Array.isArray(result.competitor_products) || !Array.isArray(result.sources)) throw new Error("Invalid live comparison response.");
        if (!controller.signal.aborted) { setData(result); setError(null); }
      })
      .catch(() => { setError("Live comparison could not be retrieved. No live prices are being shown."); })
      .finally(() => window.clearTimeout(timeout));
    return () => { controller.abort(); window.clearTimeout(timeout); };
  }, [productId]);
  const current = data?.product_id === productId ? data : null;
  return <section aria-label="Live retailer comparison" className="my-5 rounded-xl border border-slate-200 bg-white p-4">
    <div className="flex items-center gap-3"><h3 className="font-semibold">Live retailer comparison</h3><DataStatusBadge status={error ? "UNAVAILABLE" : current?.data_status ?? "UNAVAILABLE"} /></div>
    {error ? <p role="alert" className="mt-3 text-sm text-red-800">{error}</p> : !current ? <p role="status" className="mt-3 text-sm text-slate-500">Checking permitted sources…</p> : <>
      {current.reason && <p className="mt-2 text-sm text-slate-600">{current.reason}</p>}
      <ul className="my-4 space-y-2 text-xs text-slate-600">{current.sources.map(source => <li key={source.platform}><strong>{source.platform}</strong> <DataStatusBadge status={source.data_status} /> {source.reason}</li>)}</ul>
      <h4 className="mb-2 font-semibold">P&G Product — {current.pg_product.product_name}</h4>
      <OfferTable offers={current.pg_product.offers} empty="Current price, retailer product image and platform offer are unavailable." />
      <h4 className="mb-2 mt-5 font-semibold">Competitor Products</h4>
      <OfferTable offers={current.competitor_products} empty="No live competitor products were retrieved from a permitted source." />
      <p className="mt-3 text-xs text-slate-500">Development catalogue comparisons below retain their own DEMO badges.</p>
    </>}
  </section>;
}

function OfferTable({ offers, empty }: { offers: Offer[]; empty: string }) {
  return <div className="overflow-x-auto"><table className="w-full min-w-[1000px] text-left text-xs"><thead className="bg-slate-50"><tr>{["Company", "Brand", "Product Image", "Product Name", "Platform", "Package Price", "Price Per Unit", "Availability", "Last Updated", "Data Status"].map(label => <th key={label} className="p-2">{label}</th>)}</tr></thead><tbody>
    {offers.map((offer, index) => <tr key={`${offer.platform}-${offer.product_url}-${index}`} className="border-t border-slate-100">
      <td className="p-2">{offer.company || "Unknown"}</td><td className="p-2">{offer.brand || "Unknown"}</td>
      <td className="p-2"><div className="h-14 w-14"><ProductImage url={offer.product_image} name={offer.product_name} brand={offer.brand} /></div></td>
      <td className="p-2">{offer.product_url?.startsWith("https://") ? <a href={offer.product_url} target="_blank" rel="noreferrer" className="text-blue-700 underline">{offer.product_name}</a> : offer.product_name}</td>
      <td className="p-2">{offer.platform}</td><td className="p-2">{money(offer.current_price, offer.currency)}</td>
      <td className="p-2">{money(offer.price_per_unit, offer.currency)}{offer.normalized_unit ? ` / ${offer.normalized_unit}` : ""}</td>
      <td className="p-2">{offer.availability}</td><td className="p-2">{new Date(offer.collected_at).toLocaleString()}</td><td className="p-2"><DataStatusBadge status={offer.data_status} /></td>
    </tr>)}
    {!offers.length && <tr><td colSpan={10} className="p-4 text-slate-500">{empty}</td></tr>}
  </tbody></table></div>;
}
