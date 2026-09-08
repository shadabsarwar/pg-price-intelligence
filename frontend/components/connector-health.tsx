"use client";

import Link from "next/link";
import { useCollectorStatus, type CollectorStatus } from "@/hooks/use-collector-status";
import { DataStatusBadge } from "./data-status";

export function ConnectorHealth() {
  const { statuses, loading, error } = useCollectorStatus();
  return <main className="mx-auto w-full max-w-7xl px-5 py-10 sm:px-8">
    <Link href="/" className="text-sm font-medium text-blue-700">← Product dashboard</Link>
    <h1 className="mt-6 text-3xl font-semibold tracking-tight">Connector health</h1>
    <p className="mt-3 text-sm text-slate-500">Retailer access and collection status. Automatically refreshed every 10 seconds. Demo offers do not indicate live retailer access.</p>
    {loading && <p role="status" className="mt-8 text-sm text-slate-500">Loading connector status…</p>}
    {error && <p role="alert" className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">Connector status unavailable. Retrying automatically; last-known statuses must not be treated as current.</p>}
    {!loading && !error && !statuses.length && <p className="mt-8 text-slate-500">No retailer connectors registered.</p>}
    {!loading && !error && <ConnectorHealthTable statuses={statuses} />}
    <div className="mt-6 flex flex-wrap gap-2" aria-label="Status legend">{(["LIVE", "VERIFIED", "STALE", "DEMO", "UNAVAILABLE", "ERROR"] as const).map(status => <DataStatusBadge key={status} status={status} />)}</div>
    <p className="mt-3 text-xs text-slate-500">Never means no successful collection has been recorded. Request counts cover outbound requests in this backend process and reset on restart.</p>
  </main>;
}

export function ConnectorHealthTable({ statuses }: { statuses: CollectorStatus[] }) {
  return <div role="region" aria-label="Retailer connector health, scroll horizontally" tabIndex={0} className="mt-8 overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full min-w-[950px] text-left text-sm"><thead className="bg-slate-100 text-xs text-slate-500"><tr>{["Platform", "Connector Status", "Data Access", "Last Successful Collection", "Retailer Requests", "Message"].map(label => <th scope="col" key={label} className="px-4 py-3 font-medium">{label}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{statuses.map(connector => {
    const badge = connector.data_access_status === "APPROVED_SOURCE_REQUIRED" ? "UNAVAILABLE" : (["LIVE", "VERIFIED", "STALE", "DEMO", "UNAVAILABLE", "ERROR"] as const).find(value => value === connector.status) ?? "ERROR";
    return <tr key={connector.connector_name}><th scope="row" className="px-4 py-4 font-medium">{connector.platform}<p className="mt-1 text-[10px] font-normal text-slate-400">{connector.connector_name}</p></th><td className="px-4 py-4"><DataStatusBadge status={badge} /></td><td className="px-4 py-4 text-xs">{connector.data_access_status === "APPROVED_SOURCE_REQUIRED" ? "Approved source required" : connector.data_access_status}</td><td className="px-4 py-4 text-xs">{connector.last_successful_collection ? <time dateTime={connector.last_successful_collection}>{new Date(connector.last_successful_collection).toLocaleString()}</time> : "Never"}</td><td className="px-4 py-4 font-mono">{connector.retailer_requests}</td><td className="max-w-sm px-4 py-4 text-xs leading-5 text-slate-500">{connector.reason}</td></tr>;
  })}</tbody></table></div>;
}
