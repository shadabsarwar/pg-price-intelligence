"use client";

import { useEffect, useState } from "react";
import { DataStatusBadge } from "./data-status";
import type { DataStatus } from "@/types/product";

type Observation = { id: number; price: number | null; observed_at: string; source_state: DataStatus; availability: string };
type Listing = { id: number; retailer: string; latest_price: number | null; previous_price: number | null; lowest: number | null; highest: number | null;
  count: number; change_percent: number | null; unit_price: number | null; unit: string | null; data_status: DataStatus; availability: string; history: Observation[] };
const api = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const money = (value: number | null) => value === null ? "Unavailable" : `${value.toFixed(2)} QAR`;

export function PriceHistory({ productId }: { productId: number }) {
  const [data, setData] = useState<{ product_id: number; listings: Listing[] } | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${api}/products/${productId}/prices?limit=50`, { signal: controller.signal, cache: "no-store" })
      .then(response => { if (!response.ok) throw new Error(); return response.json(); })
      .then(result => { if (!Array.isArray(result.listings)) throw new Error(); if (!controller.signal.aborted) { setData(result); setError(false); } })
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [productId]);
  const listings = data?.product_id === productId ? data.listings : null;
  return <section className="mt-6 rounded-xl border border-slate-200 p-4" aria-label="Price history">
    <h3 className="text-lg font-semibold">Price history and unit prices</h3>
    <p className="mt-1 text-xs text-slate-500">Observations retain their source and collection time. Historical bounds include unavailable offers; they are not current deals.</p>
    {error ? <p role="alert" className="mt-3 text-red-800">Price history could not be loaded.</p> : !listings ? <p className="mt-3">Loading history…</p> : !listings.length ? <p className="mt-3 text-slate-500">No retailer observations yet.</p> : listings.map(listing => <details key={listing.id} className="mt-4 rounded-lg border border-slate-200 p-3">
      <summary className="cursor-pointer text-sm font-medium">{listing.retailer} · {money(listing.latest_price)} · <DataStatusBadge status={listing.data_status} /></summary>
      <dl className="my-3 grid gap-3 text-xs sm:grid-cols-3">
        <div><dt>Unit price</dt><dd>{money(listing.unit_price)}{listing.unit ? ` / ${listing.unit}` : " · Quantity unknown"}</dd></div>
        <div><dt>Previous observation</dt><dd>{money(listing.previous_price)}</dd></div>
        <div><dt>Price change</dt><dd>{listing.change_percent === null ? "Unavailable" : `${listing.change_percent.toFixed(2)}%`}</dd></div>
        <div><dt>Lowest observed</dt><dd>{money(listing.lowest)}</dd></div><div><dt>Highest observed</dt><dd>{money(listing.highest)}</dd></div>
        <div><dt>Availability</dt><dd>{listing.availability.replaceAll("_", " ")}</dd></div>
      </dl>
      <div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="mb-2 text-left text-slate-500">Latest {listing.history.length} of {listing.count} observations</caption><thead><tr>{["Observed at", "Price", "Source", "Availability"].map(label => <th key={label} className="p-2">{label}</th>)}</tr></thead>
        <tbody>{listing.history.map(row => <tr key={row.id} className="border-t border-slate-100"><td className="p-2">{new Date(row.observed_at).toLocaleString()}</td><td className="p-2">{money(row.price)}</td><td className="p-2"><DataStatusBadge status={row.source_state} /></td><td className="p-2">{row.availability.replaceAll("_", " ")}</td></tr>)}</tbody>
      </table></div>
    </details>)}
  </section>;
}
