"use client";

import Link from "next/link";
import { useState } from "react";
import { DataStatusBadge } from "@/components/data-status";
import type { DataStatus } from "@/types/product";

const api = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
type Quality = { id: number; product_name: string; source_state: DataStatus; verified: boolean; flags: string[] };
type Match = { source_product_variant_id: number; competitor_product_variant_id: number; match_score: number; match_reason: string; review_status: string; relationship_type: string };
type Run = { id: string; retailer_id: string; status: string; records_found: number; records_saved: number; errors: string | null };
type ImportResult = { total: number; imported: number; updated: number; skipped: number; dry_run: boolean; errors: { row: number; message: string }[] };
type Discovery = { id: number; product_url: string; reason: string; raw_product: string };
type Retailer = { id: string; name: string; connector: string | null };
type ImportRun = { id: string; created_at: string; source_state: string; summary: ImportResult };

export default function AdminPage() {
  const [token, setToken] = useState("");
  const [content, setContent] = useState("");
  const [format, setFormat] = useState("csv");
  const [kind, setKind] = useState("products");
  const [source, setSource] = useState("IMPORTED");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [quality, setQuality] = useState<Quality[]>([]);
  const [matches, setMatches] = useState<Match[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [discoveries, setDiscoveries] = useState<Discovery[]>([]);
  const [imports, setImports] = useState<ImportRun[]>([]);
  const [retailers, setRetailers] = useState<Retailer[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [retailer, setRetailer] = useState("");
  const [offset, setOffset] = useState(0);

  async function request(path: string, body?: unknown) {
    const response = await fetch(`${api}${path}`, { method: body === undefined ? "GET" : "POST", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-Admin-Token": token }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(120000) });
    const payload = await response.json();
    if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : `Request failed (${response.status})`);
    return payload;
  }
  async function action(task: () => Promise<void>) {
    setBusy(true); setMessage("");
    try { await task(); } catch (error) { setMessage(error instanceof Error ? error.message : "Request failed"); } finally { setBusy(false); }
  }
  async function load(pageOffset = offset) {
    const [q, m, r, d, retailers, history] = await Promise.all([request(`/quality?offset=${pageOffset}`), request(`/matches?offset=${pageOffset}&limit=100`), request("/collection-status"), request(`/discoveries?offset=${pageOffset}`), request("/retailers"), request("/imports")]);
    setQuality(q); setMatches(m); setRuns(r); setDiscoveries(d); setRetailers(retailers); setImports(history); setLoaded(true); setOffset(pageOffset);
  }
  const button = "rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm font-medium text-blue-800 disabled:opacity-50";
  const field = "mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm";
  return <main className="mx-auto max-w-6xl space-y-6 px-5 py-8">
    <Link href="/" className="text-sm text-blue-800">← Product catalogue</Link>
    <div><h1 className="text-3xl font-semibold">Catalogue administration</h1><p className="mt-2 text-sm text-slate-600">Import approved catalogue data, inspect collection results, and review product matches.</p></div>
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <label className="block text-sm font-medium">Admin token<input type="password" value={token} onChange={event => setToken(event.target.value)} autoComplete="off" className={field} /></label>
      <p className="mt-2 text-xs text-slate-500">Enter the token configured by your administrator. It stays in this page&apos;s memory.</p>
      <button className={`${button} mt-3`} disabled={busy || !token} onClick={() => void action(() => load())}>Load / refresh administration data</button>
    </section>
    {message && <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{message}</p>}
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="text-xl font-semibold">Import catalogue</h2>
      <p className="mt-2 text-sm text-slate-500">Required columns: company, brand, category, product_name. Add size, unit, pack_count, variant_name, barcode, subcategory, purpose and attributes where known. Prices also require retailer and retailer_sku or product_url.</p>
      <div className="my-3 grid gap-3 sm:grid-cols-3">
        <label className="text-sm">Catalogue<select className={field} value={kind} onChange={e => { setKind(e.target.value); setResult(null); }}><option value="products">P&G</option><option value="competitors">Competitors</option></select></label>
        <label className="text-sm">Format<select className={field} value={format} onChange={e => { setFormat(e.target.value); setResult(null); }}><option value="csv">CSV</option><option value="json">JSON</option></select></label>
        <label className="text-sm">Source<select className={field} value={source} onChange={e => { setSource(e.target.value); setResult(null); }}><option>IMPORTED</option><option>MANUAL</option><option>DEMO</option></select></label>
      </div>
      <label className="block text-sm">Choose file<input type="file" accept=".csv,.json" className="ml-3 text-sm" onChange={e => {
        const file = e.target.files?.[0]; if (!file) return;
        if (file.size > 20_000_000) { setMessage("Use the local import command for files larger than 20 MB."); return; }
        void action(async () => { setContent(await file.text()); setFormat(file.name.endsWith(".json") ? "json" : "csv"); setResult(null); });
      }} /></label>
      <label className="mt-3 block text-sm">CSV or JSON contents<textarea className={`${field} h-40 font-mono text-xs`} value={content} onChange={e => { setContent(e.target.value); setResult(null); }} /></label>
      <div className="mt-3 flex gap-3"><button className={button} disabled={busy || !content || !token} onClick={() => void action(async () => { setResult(await request(`/imports/${kind}`, { format, content, source_state: source, dry_run: true })); })}>Validate (dry run)</button>
        <button className={button} disabled={busy || !result?.dry_run || !token} onClick={() => void action(async () => { setResult(await request(`/imports/${kind}`, { format, content, source_state: source, dry_run: false })); await load(); })}>Import valid rows</button></div>
      {result && <div role="status" className="mt-4 text-sm"><p>{result.dry_run ? "Dry run" : "Import complete"}: {result.total} rows · {result.imported} new · {result.updated} updated · {result.skipped} skipped · {result.errors.length} errors</p><ul className="mt-2 max-h-60 overflow-auto text-red-800">{result.errors.map(e => <li key={e.row}>Row {e.row}: {e.message}</li>)}</ul></div>}
    </section>
    <section className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="text-xl font-semibold">Retailer collection</h2>
      <div className="my-3 grid gap-3 sm:grid-cols-3"><label className="text-sm">Retailer<select className={field} value={retailer} onChange={e => setRetailer(e.target.value)}><option value="">Choose a configured connector</option>{retailers.filter(r => r.connector).map(r => <option key={r.id} value={r.connector!}>{r.name}</option>)}</select></label>
        <label className="text-sm">Search query<input className={field} value={query} onChange={e => setQuery(e.target.value)} /></label><label className="text-sm">Category context<input className={field} value={category} onChange={e => setCategory(e.target.value)} /></label></div>
      <button className={button} disabled={busy || !retailer || query.trim().length < 2} onClick={() => void action(async () => { await request("/collection/run", { retailers: [retailer], query, category: category || null }); setMessage("Collection queued. Refresh to see progress."); await load(); })}>Queue collection</button>
      <p className="mt-2 text-xs text-slate-500">Category context is reviewed input. Unknown brand or company stays in the discovery review queue. Unconfigured sources report UNAVAILABLE.</p>
      {runs.map(run => <div key={run.id} className="mt-3 border-t border-slate-100 pt-3 text-sm"><strong>{run.retailer_id}</strong> · {run.status} · {run.records_found} found / {run.records_saved} saved {['ERROR', 'UNAVAILABLE', 'PARTIAL'].includes(run.status) && <button className={button} disabled={busy} onClick={() => void action(async () => { await request(`/collection/${run.id}/retry`, {}); await load(); })}>Retry</button>}<p className="mt-1 break-words text-xs text-slate-500">{run.errors}</p></div>)}
    </section>
    <section className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="text-xl font-semibold">Data quality and unmatched products</h2>
      {loaded && !quality.length && <p className="mt-3 text-sm">No flagged products in this page of the catalogue.</p>}
      {quality.map(item => <div key={item.id} className="mt-3 border-t border-slate-100 pt-3 text-sm"><strong>#{item.id} {item.product_name}</strong> <DataStatusBadge status={item.source_state} /><p className="my-2 text-xs text-amber-800">{item.flags.join(" · ")}</p>{!item.verified && item.source_state !== "DEMO" && <button className={button} disabled={busy} onClick={() => void action(async () => { await request(`/products/${item.id}/verify`, {}); await load(); })}>Mark identity verified</button>}</div>)}
    </section>
    <section className="rounded-xl border border-slate-200 bg-white p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">Competitor match review</h2><button className={button} disabled={busy || !token} onClick={() => void action(async () => { await request("/matches/recalculate", {}); await load(); })}>Recalculate matches</button></div>
      {loaded && !matches.length && <p className="mt-3 text-sm">No candidate relationships in this page.</p>}
      {matches.map(match => <div key={`${match.source_product_variant_id}-${match.competitor_product_variant_id}`} className="mt-3 border-t border-slate-100 pt-3 text-sm"><p>#{match.source_product_variant_id} → #{match.competitor_product_variant_id} · {(match.match_score * 100).toFixed(1)}% rule agreement · {match.relationship_type} · {match.review_status}</p><p className="my-2 break-words text-xs text-slate-500">{match.match_reason}</p><div className="flex gap-2">{["approved", "rejected", "pending"].map(decision => <button key={decision} className={button} disabled={busy} onClick={() => void action(async () => { await request(`/matches/${match.source_product_variant_id}/${match.competitor_product_variant_id}/review`, { decision }); await load(); })}>{decision === "approved" ? "Approve" : decision === "rejected" ? "Reject" : "Reset review"}</button>)}</div></div>)}
    </section>
    <section className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="text-xl font-semibold">Discoveries requiring enrichment</h2><p className="mt-2 text-sm text-slate-500">Use the retained evidence to prepare a reviewed catalogue import, preserving its retailer URL. No unverified identity is attached automatically.</p>
      {discoveries.map(item => <details key={item.id} className="mt-3 text-sm"><summary className="cursor-pointer">#{item.id} · {item.reason}</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap break-all text-xs">{item.raw_product}</pre></details>)}
    </section>
    {loaded && <div className="flex items-center gap-3 text-sm"><button className={button} disabled={busy || offset === 0} onClick={() => void action(() => load(Math.max(0, offset - 100)))}>Previous page</button><span>Review offset: {offset}</span><button className={button} disabled={busy} onClick={() => void action(() => load(offset + 100))}>Next page</button></div>}
    <section className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="text-xl font-semibold">Recent import reports</h2>{imports.map(run => <details key={run.id} className="mt-3 text-sm"><summary className="cursor-pointer">{new Date(run.created_at).toLocaleString()} · {run.source_state} · {run.summary.total} rows · {run.summary.errors.length} errors{run.summary.dry_run ? " · Dry run" : ""}</summary><pre className="mt-2 overflow-auto text-xs">{JSON.stringify(run.summary, null, 2)}</pre></details>)}</section>
  </main>;
}
