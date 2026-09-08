import type { DataStatus } from "@/types/product";

export function DataStatusBadge({ status }: { status: DataStatus }) {
  const color = status === "ERROR" || status === "UNAVAILABLE" ? "bg-red-50 text-red-800"
    : status === "STALE" || status === "DEMO" ? "bg-amber-50 text-amber-800"
    : status === "LIVE" || status === "COLLECTED" ? "bg-emerald-50 text-emerald-800"
    : "bg-blue-50 text-blue-800";
  return <span className={`inline-flex rounded-md px-2 py-1 text-[10px] font-semibold tracking-wide ${color}`}>{status}</span>;
}
