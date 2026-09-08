"use client";

import { useState } from "react";
import Link from "next/link";
import { useProducts } from "@/hooks/use-products";
import { DashboardIcon, LiveBadge, type IconName } from "./dashboard-icon";
import { ProductCard } from "./product-card";
import { PriceComparison } from "./price-comparison";
import { compareProduct } from "@/lib/comparison";
import { CompetitorIntelligence } from "./competitor-intelligence";
import { RetailerAvailability } from "./retailer-availability";

function SummaryCard({ label, value, detail, icon }: { label: string; value: string; detail: string; icon: IconName }) {
  return <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-center justify-between gap-2"><p className="text-sm font-medium text-slate-500">{label}</p><span className="rounded-lg bg-blue-50 p-2 text-blue-700"><DashboardIcon name={icon} className="h-4 w-4" /></span></div><p className="mt-3 text-3xl font-semibold tracking-tight text-slate-900">{value}</p><p className="mt-2 text-xs text-slate-500">{detail}</p></div>;
}

export default function ProductDashboard() {
  const { products, loading, refreshing, error, updatedAt, updatedLabel, live, refresh, now } = useProducts();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selectedProduct = products.find(product => product.id === selectedId);
  const [intelligenceId, setIntelligenceId] = useState<number | null>(null);
  const intelligenceProduct = products.find(product => product.id === intelligenceId);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [visibleCount, setVisibleCount] = useState(24);
  const categories = [...new Set(products.map(product => product.category))].sort();
  const query = search.trim().toLowerCase();
  const visible = products.filter(product => (!category || product.category === category)
    && (!query || `${product.product_name} ${product.brand}`.toLowerCase().includes(query)));
  const bestPrices = products.filter(product => product.currency === "QAR").map(compareProduct);
  const summarySource = bestPrices.some(item => item.source === "verified") ? "verified" : "demo";
  const prices = bestPrices.filter(item => item.source === summarySource && item.lowest !== null).map(item => item.lowest!);
  const average = prices.length ? prices.reduce((sum, price) => sum + price, 0) / prices.length : null;
  const demoMode = products.some(product => product.listings?.some(item => item.data_source === "demo"));
  const hasData = updatedAt !== null;

  return <div className="min-h-screen">
    <a href="#catalogue" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-4">Skip to product catalogue</a>
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-5 py-5 sm:px-8">
        <Link href="/" className="flex items-center gap-3" aria-label="P&G Price Intelligence home"><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#003da6] text-lg font-bold italic text-white">P&G</span><div><p className="text-sm font-bold tracking-tight sm:text-base">P&G Price Intelligence</p><p className="mt-0.5 text-[10px] uppercase tracking-[0.2em] text-slate-500">Market intelligence platform</p></div></Link>
        <div className="flex items-center gap-4"><div className="hidden text-right sm:block"><p className="text-xs font-medium text-slate-600">{updatedLabel}</p><p className="mt-1 text-[10px] text-slate-400">Automatic refresh every 10 seconds</p></div><LiveBadge live={live} label={loading ? "Connecting" : live ? "Live API" : "Disconnected"} /><span className="hidden h-8 w-px bg-slate-200 sm:block" /><span className="hidden rounded-full bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-600 sm:block">PG</span></div>
      </div>
      <nav aria-label="Main navigation" className="mx-auto flex max-w-7xl items-center gap-7 px-5 sm:px-8"><a href="#catalogue" aria-current="page" className="flex items-center gap-2 border-b-2 border-blue-700 pb-3 pt-1 text-sm font-semibold text-blue-700"><DashboardIcon name="grid" className="h-4 w-4" />Product catalogue</a><Link href="/admin" className="pb-3 pt-1 text-sm font-medium text-slate-600">Administration</Link><span className="ml-auto pb-3 text-xs text-slate-500">Qatar market <span className="ml-1 text-slate-300">/</span> QAR</span></nav>
    </header>

    <main className="mx-auto max-w-7xl px-5 py-8 sm:px-8 sm:py-10">
      <RetailerAvailability />
      <section className="mb-7 flex flex-wrap items-end justify-between gap-5">
        <div><p className="mb-2 text-[10px] font-bold uppercase tracking-[0.22em] text-blue-700">Catalogue overview</p><h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Your products. In focus.</h1><p className="mt-3 text-sm leading-6 text-slate-500">Your product portfolio, with platform prices side by side.</p></div>
        <button onClick={() => void refresh()} disabled={refreshing} className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-50 disabled:opacity-50"><DashboardIcon name="refresh" className="h-4 w-4" />{refreshing ? "Refreshing…" : "Refresh data"}</button>
      </section>

      {demoMode && <p className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"><strong>Demo catalogue.</strong> Platform prices and availability are synthetic, not live market offers. The Live API indicator refers only to the dashboard connection.</p>}
      <section aria-label="Catalogue summary" className="mb-8 grid grid-cols-1 gap-4 min-[400px]:grid-cols-2 lg:grid-cols-4">
        <SummaryCard label="Total Products" value={hasData ? String(products.length).padStart(2, "0") : "—"} detail="Across your product portfolio" icon="box" />
        <SummaryCard label="Categories" value={hasData ? String(categories.length).padStart(2, "0") : "—"} detail="Distinct product categories" icon="grid" />
        <SummaryCard label="Average Best Price" value={average === null ? "—" : `${average.toFixed(2)} QAR`} detail={`Available ${summarySource === "demo" ? "demo" : "recorded"} offers in QAR only`} icon="chart" />
        <SummaryCard label="API Monitoring Status" value={loading ? "Connecting" : live ? "Active" : "Offline"} detail={live ? "Checking for updates every 10 seconds" : "Waiting for a successful connection"} icon="pulse" />
      </section>

      <section id="catalogue" aria-labelledby="catalogue-title">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-3"><h2 id="catalogue-title" className="text-xl font-semibold tracking-tight">Product catalogue</h2><span className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-500">{hasData ? products.length : "—"} products</span></div><p className="flex items-center gap-1.5 text-xs text-slate-500"><DashboardIcon name="pulse" className="h-3.5 w-3.5" />{updatedLabel}</p></div>
        <div className="mb-6 flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-3 sm:flex-row">
          <div className="relative flex-1"><label className="sr-only" htmlFor="product-search">Search by product name or brand</label><span className="pointer-events-none absolute left-3 top-3 text-slate-400"><DashboardIcon name="search" className="h-4 w-4" /></span><input id="product-search" type="search" value={search} onChange={event => { setSearch(event.target.value); setVisibleCount(24); }} placeholder="Search products or brands…" className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50/70 pl-10 pr-3 text-sm placeholder:text-slate-400" /></div>
          <div><label className="sr-only" htmlFor="category-filter">Filter by category</label><select id="category-filter" value={category} onChange={event => { setCategory(event.target.value); setVisibleCount(24); }} className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-600 sm:w-52"><option value="">All categories</option>{category && !categories.includes(category) && <option value={category}>{category}</option>}{categories.map(item => <option key={item} value={item}>{item}</option>)}</select></div>
        </div>

        {error && <div role="alert" className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><div><p className="font-semibold">Unable to refresh products</p><p className="mt-1">{hasData ? "Showing the last successfully loaded catalogue. " : "Check that the backend is running. "}{error} Retrying every 10 seconds.</p></div><button onClick={() => void refresh()} disabled={refreshing} className="rounded-lg border border-amber-300 px-3 py-2 font-medium disabled:opacity-50">Retry now</button></div>}

        {loading ? <div role="status" aria-label="Loading products"><p className="sr-only">Loading products</p><div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">{[1, 2, 3].map(item => <div key={item} className="overflow-hidden rounded-2xl border border-slate-200 bg-white"><div className="h-56 bg-slate-100" /><div className="space-y-5 p-6"><div className="h-3 w-20 rounded bg-slate-100" /><div className="h-5 w-3/4 rounded bg-slate-100" /><div className="h-8 w-1/2 rounded bg-slate-100" /><div className="h-10 rounded bg-slate-50" /></div></div>)}</div></div>
          : visible.length ? <><p className="mb-4 text-xs text-slate-500" role="status">Showing {Math.min(visibleCount, visible.length)} of {visible.length} matching products</p><div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">{visible.slice(0, visibleCount).map(product => <ProductCard key={product.id} product={product} live={live} updatedLabel={updatedLabel} now={now} onCompare={() => setSelectedId(product.id)} onCompetitors={() => setIntelligenceId(product.id)} />)}</div>{visibleCount < visible.length && <button onClick={() => setVisibleCount(count => count + 24)} className="mt-6 rounded-lg border border-blue-200 bg-white px-4 py-3 text-sm font-semibold text-blue-800">Show more products</button>}</>
            : (!error || hasData) && <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center"><DashboardIcon name="box" className="mx-auto mb-4 h-9 w-9 text-slate-400" /><h3 className="text-lg font-semibold">{products.length ? "No matching products" : "Your catalogue is ready to grow"}</h3><p className="mt-2 text-sm text-slate-500">{products.length ? "Try another product name, brand, or category." : "Import your catalogue from the Administration page. Products will appear here automatically."}</p>{(search || category) && <button onClick={() => { setSearch(""); setCategory(""); }} className="mt-5 text-sm font-semibold text-blue-700">Clear filters</button>}</div>}
      </section>
      <footer className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-5 text-[11px] text-slate-500"><span>P&G Price Intelligence <span className="mx-2 text-slate-300">/</span> Product catalogue</span><span>Update times reflect API refreshes · Prices as supplied by the catalogue</span></footer>
      {selectedProduct && <PriceComparison product={selectedProduct} now={now} live={live} refreshing={refreshing} updatedLabel={updatedLabel} onClose={() => setSelectedId(null)} />}
      {intelligenceProduct && <CompetitorIntelligence key={intelligenceProduct.id} product={intelligenceProduct} now={now} onClose={() => setIntelligenceId(null)} />}
    </main>
  </div>;
}




