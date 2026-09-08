"use client";

import { useState } from "react";
import { safeImageUrl } from "@/lib/comparison";
import { DashboardIcon } from "./dashboard-icon";

export function ProductImage({ url, name, brand, compact = false }: { url?: string | null; name: string; brand: string; compact?: boolean }) {
  const source = safeImageUrl(url);
  // Remount image state when a polled URL changes, including a return to an old URL.
  return <ImageContent key={source ?? "missing"} source={source} name={name} brand={brand} compact={compact} />;
}

function ImageContent({ source, name, brand, compact }: { source?: string; name: string; brand: string; compact: boolean }) {
  const [state, setState] = useState<"loading" | "loaded" | "error">("loading");
  const fallback = !source || state === "error";
  return <div className="relative flex h-full w-full items-center justify-center overflow-hidden rounded-lg bg-slate-50">
    {fallback ? <div className="flex flex-col items-center gap-3 text-blue-800" aria-label={`${brand} image unavailable`}>
      <div className={`relative flex items-center justify-center rounded-2xl border border-blue-100 bg-white ${compact ? "h-10 w-10 text-xl" : "h-24 w-24 text-5xl"}`}><span className="font-semibold">{brand.trim().charAt(0).toUpperCase() || "P"}</span>{!compact && <DashboardIcon name="box" className="absolute -bottom-2 -right-2 h-8 w-8 rounded-lg bg-white p-1 shadow-sm" />}</div>
      {!compact && <span className="text-[10px] uppercase tracking-widest text-slate-500">{state === "error" ? "Image unavailable" : "Image not supplied"}</span>}
    </div> : <>
      {state === "loading" && <span role="status" className="absolute inset-0 flex items-center justify-center bg-slate-100 text-xs text-slate-500">{compact ? "…" : "Loading image…"}</span>}
      {/* Arbitrary approved feed hosts are supported without an image proxy. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={source} alt={name} loading="lazy" onLoad={() => setState("loaded")} onError={() => setState("error")} className={`h-full w-full object-contain ${compact ? "p-1" : "p-6"} ${state === "loaded" ? "opacity-100" : "opacity-0"}`} />
    </>}
  </div>;
}
