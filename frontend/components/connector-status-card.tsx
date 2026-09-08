import type { CollectorStatus } from "@/hooks/use-collector-status";
import { DataStatusBadge } from "./data-status";

export function ConnectorStatusCard({ connector }: { connector: CollectorStatus }) {
  const requiresSource = connector.data_access_status === "APPROVED_SOURCE_REQUIRED";
  const known = ["LIVE", "VERIFIED", "STALE", "DEMO", "UNAVAILABLE", "ERROR"] as const;
  const badge = requiresSource ? "UNAVAILABLE" : known.find(value => value === connector.status) ?? "ERROR";
  return <div className="mb-4 rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-700">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{connector.platform}: {requiresSource ? "Live data unavailable" : badge === "LIVE" ? "Live retailer data" : "Retailer collection status"}</h3><DataStatusBadge status={badge} /></div>
    <p className="mt-2">{requiresSource ? "An approved retailer API or product data source is required before live prices can be collected." : connector.reason}</p>
    <ul className="mt-3 space-y-1 text-xs text-slate-500">
      <li>{connector.retailer_requests === 0 ? "No retailer request was made" : `Retailer requests: ${connector.retailer_requests}`}</li>
      <li>Demo data is separate from live data</li>
      <li>Last successful collection: {connector.last_successful_collection ? <time dateTime={connector.last_successful_collection}>{new Date(connector.last_successful_collection).toLocaleString()}</time> : "Never"}</li>
    </ul>
  </div>;
}
