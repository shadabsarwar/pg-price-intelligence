"use client";

import Link from "next/link";
import { useCollectorStatus } from "@/hooks/use-collector-status";
import { ConnectorStatusCard } from "./connector-status-card";

export function RetailerAvailability({ platforms }: { platforms?: string[] }) {
  const { statuses, loading, error } = useCollectorStatus();
  const visible = platforms ? statuses.filter(connector => platforms.includes(connector.platform)) : statuses.filter(connector => connector.connector_name === "lulu_qatar");
  return <section aria-label="Retailer data access" className="mb-4">
    {loading && <p role="status" className="mb-3 text-xs text-slate-500">Checking retailer data access…</p>}
    {error && <p role="alert" className="mb-3 rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-600">Live data unavailable. Connector status could not be checked; retrying automatically. Demo data remains separate.</p>}
    {!loading && !error && visible.map(connector => <ConnectorStatusCard key={connector.connector_name} connector={connector} />)}
    {!loading && !error && !visible.length && <p className="mb-3 text-sm text-slate-500">No registered retailer connector status is available for these platforms.</p>}
    <Link href="/connectors" className="text-xs font-semibold text-blue-700 underline underline-offset-4">View all connector health</Link>
  </section>;
}
