"use client";

import { useEffect, useRef, useState } from "react";
import { useIntelligence } from "@/hooks/use-intelligence";
import type { CompetitorComparison, CompetitorMatch } from "@/types/intelligence";
import type { Product } from "@/types/product";
import { relativeTime } from "@/lib/comparison";
import { ProductImage } from "./product-image";
import { DataStatusBadge } from "./data-status";
import { PriceComparison } from "./price-comparison";
import { LiveComparison } from "./live-comparison";

const tabs = ["Overview", "Platform Prices", "Competitors", "Price History"] as const;
const money = (value: number | null, currency: string) => value === null ? "Unavailable" : `${value.toFixed(2)} ${currency}`;
const signed = (value: number | null) => value === null ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(2)}`;

export function CompetitorIntelligence({ product, now, onClose }: { product: Product; now: number; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const { data, error, refreshing, updatedAt, refresh } = useIntelligence(product.id);
  const [tab, setTab] = useState<typeof tabs[number]>("Competitors");
  const [platformProductId, setPlatformProductId] = useState<number | null>(null);
  const current = data?.pg_product.product ?? product;
  const platformProduct = platformProductId === current.id ? current : data?.competitors.find(item => item.product.id === platformProductId)?.product;
  const connected = !!updatedAt && !error && now - updatedAt < 25000;
  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    element?.showModal();
    document.body.style.overflow = "hidden";
    return () => { element?.close(); document.body.style.overflow = overflow; previous?.focus(); };
  }, []);
  return <dialog ref={dialog} onCancel={event => { event.preventDefault(); onClose(); }} aria-labelledby="intelligence-title" className="fixed inset-0 m-auto max-h-[94dvh] w-[calc(100%_-_1rem)] max-w-7xl overflow-y-auto rounded-2xl bg-slate-50 p-0 text-slate-900 shadow-2xl backdrop:bg-slate-950/60">
    <header className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-slate-200 bg-white px-5 py-4"><div><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">P&G · Competitor intelligence</p><h2 id="intelligence-title" className="mt-1 text-lg font-semibold">{current.product_name}</h2></div><button autoFocus onClick={onClose} className="rounded-lg border border-slate-200 px-3 py-2 text-sm">Close ×</button></header>
    <div className="p-5 sm:p-7">
      <LiveComparison key={product.id} productId={product.id} />
      <div className="flex flex-wrap items-center gap-5"><div className="h-32 w-32 shrink-0"><ProductImage url={current.image_url} name={current.product_name} brand={current.brand} /></div><div className="min-w-0 flex-1"><p className="text-xs font-bold uppercase tracking-widest text-blue-700">{current.brand} / {current.company}</p><h3 className="mt-2 text-2xl font-semibold">{current.product_name}</h3><p className="mt-2 text-sm text-slate-500">{current.category} · {current.subcategory || "Unspecified type"} · {current.size}</p><p className="mt-1 text-xs text-slate-500">Pack quantity: {current.pack_quantity ?? "Unknown"} · {current.purpose || "Purpose not supplied"}</p><div className="mt-3 flex flex-wrap items-center gap-3"><DataStatusBadge status={data?.data_status ?? current.data_status ?? "ERROR"} /><span className="text-xs text-slate-500">{connected ? "API connected" : "API not connected"} · API refresh: {relativeTime(updatedAt, now)}</span></div></div><button onClick={() => void refresh()} disabled={refreshing} className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm disabled:opacity-50">{refreshing ? "Refreshing…" : "Refresh intelligence"}</button></div>
      <p className="my-5 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">Development catalogue: sample specifications, diaper counts and prices are DEMO, not verified Qatar offers. Match confidence is a rule score, not an AI probability. API connectivity does not indicate live market collection.</p>
      <div role="tablist" aria-label="Product intelligence sections" className="mb-6 flex overflow-x-auto border-b border-slate-200">{tabs.map((label, index) => <button key={label} id={`intelligence-tab-${index}`} role="tab" aria-selected={tab === label} aria-controls={`intelligence-panel-${index}`} tabIndex={tab === label ? 0 : -1} onKeyDown={event => {
        let next = index;
        if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
        else if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = tabs.length - 1;
        else return;
        event.preventDefault(); setTab(tabs[next]); document.getElementById(`intelligence-tab-${next}`)?.focus();
      }} onClick={() => setTab(label)} className={`whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium ${tab === label ? "border-blue-700 text-blue-800" : "border-transparent text-slate-500"}`}>{label}</button>)}</div>
      {error && <div role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error} {data ? "Showing the last successful response." : "Retrying every 10 seconds."}</div>}
      {!data && !error && <p role="status" className="py-16 text-center text-slate-500">Loading competitor intelligence…</p>}
      {data && <section role="tabpanel" id={`intelligence-panel-${tabs.indexOf(tab)}`} aria-labelledby={`intelligence-tab-${tabs.indexOf(tab)}`} tabIndex={0}>
        {(tab === "Overview" || tab === "Competitors") && <MarketSummary data={data} />}
        {tab === "Overview" && <div className="mt-6 rounded-xl border border-slate-200 bg-white p-5"><h3 className="font-semibold">How these products are matched</h3><p className="mt-2 text-sm leading-7 text-slate-600">Candidates must have a different company and brand, with matching category, subcategory, purpose, unit dimension and essential product attributes. Scores combine category (20), subcategory (20), purpose (20), size similarity (15), pack quantity (10), attributes (10) and variant (5).</p><p className="mt-3 text-sm text-slate-600">Registered competing companies: {data.competitor_companies.map(company => company.name).join(", ") || "No eligible matches"}.</p><p className="mt-3 text-xs text-slate-500">Fresh verified offers are evaluated separately from demo offers. Missing quantities, mixed currencies, stale observations and unavailable products are excluded from market ranking.</p></div>}
        {tab === "Platform Prices" && <div className="rounded-xl border border-slate-200 bg-white p-6"><h3 className="text-lg font-semibold">P&G platform prices</h3><p className="mt-2 text-sm text-slate-500">Best package price: {money(data.pg_product.best_price, current.currency)} · {data.pg_product.platforms_found} platforms</p><SourceSummary product={current} now={now} /><button onClick={() => setPlatformProductId(current.id)} className="mt-4 rounded-lg bg-blue-800 px-4 py-2 text-sm font-semibold text-white">View Platform Prices</button></div>}
        {tab === "Price History" && <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center"><h3 className="text-lg font-semibold">Price history is not collected yet</h3><p className="mt-2 text-sm text-slate-500">Only the latest in-memory observations are stored. No historical prices or charts have been fabricated.</p></div>}
        {tab === "Competitors" && <CompetitorTable data={data} now={now} onPlatforms={setPlatformProductId} />}
      </section>}
      {platformProduct && <PriceComparison product={platformProduct} now={now} live={connected} refreshing={refreshing} updatedLabel={relativeTime(updatedAt, now)} onClose={() => setPlatformProductId(null)} />}
    </div>
  </dialog>;
}

export function MarketSummary({ data }: { data: CompetitorComparison }) {
  const market = data.market_position;
  const currency = data.pg_product.product.currency;
  const unit = market.normalized_unit ? `${currency} / ${market.normalized_unit}` : currency;
  return <div><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[
    ["P&G best package price", money(market.pg_price, currency)],
    ["P&G unit price", money(market.pg_normalized_price, unit)],
    ["Competitor unit average", money(market.market_average, unit)],
    ["Cheapest competitor per unit", money(market.cheapest_competitor, unit)],
  ].map(([label, value]) => <div key={label} className="rounded-xl border border-slate-200 bg-white p-4"><p className="text-xs text-slate-500">{label}</p><p className="mt-2 text-lg font-semibold">{value}</p></div>)}</div><p className="mt-3 text-sm text-slate-600">{market.percentage_above_market === null ? "Not enough comparable price data to calculate market position." : `P&G is ${Math.abs(market.percentage_above_market).toFixed(1)}% ${market.percentage_above_market >= 0 ? "above" : "below"} the competitor unit-price average.`} <span className="text-xs text-slate-500">Based on {market.comparable_competitor_count} comparable competitor products, excluding P&G.</span></p></div>;
}

export function CompetitorTable({ data, now, onPlatforms }: { data: CompetitorComparison; now: number; onPlatforms: (id: number) => void }) {
  if (!data.competitors.length) return <div className="mt-6 rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center"><h3 className="font-semibold">No equivalent competitors found</h3><p className="mt-2 text-sm text-slate-500">Check the structured category, purpose, quantity and essential attributes before adding comparable products.</p></div>;
  return <div className="mt-6"><h3 className="text-lg font-semibold">Competing products <span className="text-sm font-normal text-slate-500">({data.competitors.length})</span></h3><p className="mb-4 mt-2 text-xs text-slate-500">Differences are competitor minus P&G. Package prices can differ because of size; use unit differences for value comparisons.</p><div role="region" aria-label="Competitor comparison table, scroll horizontally" tabIndex={0} className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full min-w-[1350px] text-left text-sm"><thead className="bg-slate-100 text-xs text-slate-500"><tr>{["Product Image", "Company / Brand / Product", "Match Confidence", "Size", "Best Price", "Price Per Unit", "Platforms Found", "Price Difference", "Last Updated"].map(label => <th scope="col" key={label} className="px-4 py-3 font-medium">{label}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{data.competitors.map(item => <CompetitorRow key={item.product.id} item={item} now={now} onPlatforms={onPlatforms} />)}</tbody></table></div></div>;
}

function CompetitorRow({ item, now, onPlatforms }: { item: CompetitorMatch; now: number; onPlatforms: (id: number) => void }) {
  const product = item.product;
  return <tr className={item.highlights.includes("Best value per unit") ? "bg-emerald-50/40" : ""}><td className="px-4 py-4"><div className="h-20 w-20"><ProductImage url={product.image_url} name={product.product_name} brand={product.brand} compact /></div></td><th scope="row" className="max-w-60 px-4 py-4 font-normal"><p className="text-xs text-slate-500">{product.company}</p><p className="mt-1 text-xs font-bold uppercase text-blue-700">{product.brand}</p><p className="mt-1 font-semibold">{product.product_name}</p><div className="mt-2 flex flex-wrap gap-1">{item.highlights.map(label => <span key={label} className="rounded bg-blue-50 px-1.5 py-1 text-[10px] text-blue-800">{label}</span>)}</div></th><td className="px-4 py-4"><p className="font-semibold">{item.match_confidence.toFixed(1)} / 100</p><details className="mt-2 max-w-52 text-xs text-slate-500"><summary className="cursor-pointer text-blue-700">Why matched?</summary><p className="my-2">{item.match_explanation}</p>{Object.entries(item.match_breakdown).map(([key, value]) => <p key={key}>{key.replaceAll("_", " ")}: {value}</p>)}</details></td><td className="px-4 py-4 text-xs">{product.size}<p className="mt-1 text-slate-500">Pack: {product.pack_quantity ?? "Unknown"}</p></td><td className="whitespace-nowrap px-4 py-4"><p className="font-semibold">{money(item.best_price, product.currency)}</p><p className="mt-1 text-[10px] text-slate-500">High: {money(item.highest_price, product.currency)}</p><div className="mt-2"><DataStatusBadge status={item.data_status} /></div></td><td className="px-4 py-4 font-medium">{money(item.normalized_price, product.currency)}<p className="text-xs font-normal text-slate-500">per {item.normalized_unit ?? "unknown unit"}</p></td><td className="px-4 py-4"><p>{item.platforms_found} platforms</p><button onClick={() => onPlatforms(product.id)} className="mt-2 text-xs font-semibold text-blue-700 underline underline-offset-4">View Platform Prices</button></td><td className="px-4 py-4 text-xs">{item.comparable_prices ? <><p>Package: {signed(item.price_difference)} {product.currency}</p><p className="mt-1 text-slate-500">{signed(item.percentage_difference)}%</p><p className="mt-2 font-medium">Per unit: {signed(item.normalized_difference)} {product.currency}</p><p className="mt-1 text-slate-500">{signed(item.normalized_percentage_difference)}%</p></> : "Prices not comparable"}</td><td className="min-w-48 px-4 py-4"><p className="text-xs">{relativeTime(item.last_updated ? Date.parse(item.last_updated) : null, now)}</p><SourceSummary product={product} now={now} /></td></tr>;
}

function SourceSummary({ product, now }: { product: Product; now: number }) {
  return <ul className="mt-3 space-y-2 text-[10px] text-slate-500">{product.listings?.map(item => <li key={`${item.platform}-${item.platform_product_id}`}><span className="font-medium">{item.platform}</span> · <DataStatusBadge status={item.data_status ?? (item.data_source === "demo" ? "DEMO" : "VERIFIED")} /><p>{item.source_name ?? item.data_source} · {relativeTime(Date.parse(item.last_updated), now)}</p></li>)}</ul>;
}
