"use client";

import { useEffect, useState } from "react";

interface ServiceStatus {
  name: string;
  status: "ok" | "error" | "loading";
  detail?: string;
  latency?: number;
}

export default function SystemStatus() {
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [lastCheck, setLastCheck] = useState<Date | null>(null);

  const checkServices = async () => {
    const checks: ServiceStatus[] = [];

    // API Health
    const t0 = Date.now();
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      checks.push({ name: "API", status: data.status === "ok" ? "ok" : "error", latency: Date.now() - t0 });
    } catch {
      checks.push({ name: "API", status: "error", detail: "Backend unreachable" });
    }

    // MT5 Connection
    try {
      const t1 = Date.now();
      const res = await fetch("/api/mt5/account");
      const data = await res.json();
      checks.push({
        name: "MT5",
        status: data.connected ? "ok" : "error",
        detail: data.connected ? `#${data.account?.login} $${data.account?.equity?.toLocaleString()}` : "Not connected",
        latency: Date.now() - t1,
      });
    } catch {
      checks.push({ name: "MT5", status: "error", detail: "Endpoint unavailable" });
    }

    // Signals
    try {
      const t2 = Date.now();
      const res = await fetch("/api/signals/portfolio");
      const data = await res.json();
      const nComponents = data.components?.length ?? 0;
      checks.push({
        name: "Signals",
        status: nComponents > 0 ? "ok" : "error",
        detail: `${nComponents} components | ${data.timestamp?.slice(0, 19) ?? "?"}`,
        latency: Date.now() - t2,
      });
    } catch {
      checks.push({ name: "Signals", status: "error", detail: "Signal engine down" });
    }

    // Exports
    try {
      const res = await fetch("/api/exports/strategies");
      const data = await res.json();
      checks.push({ name: "Exports", status: "ok", detail: `${data.length} strategies loaded` });
    } catch {
      checks.push({ name: "Exports", status: "error" });
    }

    // Tickers
    try {
      const res = await fetch("/api/data/tickers");
      const data = await res.json();
      checks.push({ name: "Tickers", status: "ok", detail: `${data.all_tickers?.length} tickers, ${Object.keys(data.categories || {}).length} categories` });
    } catch {
      checks.push({ name: "Tickers", status: "error" });
    }

    setServices(checks);
    setLastCheck(new Date());
  };

  useEffect(() => {
    checkServices();
    const interval = setInterval(checkServices, 60000);
    return () => clearInterval(interval);
  }, []);

  const allOk = services.every((s) => s.status === "ok");
  const errorCount = services.filter((s) => s.status === "error").length;

  return (
    <div className="fixed bottom-0 left-56 right-0 z-50">
      {/* Collapsed bar */}
      <div
        className={`flex items-center justify-between px-4 py-1.5 cursor-pointer text-[10px] font-mono border-t transition-all ${
          allOk
            ? "bg-cyber-surface/95 border-cyber-border text-cyber-dim"
            : "bg-red-900/20 border-red-500/30 text-red-400"
        }`}
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <span className={`w-1.5 h-1.5 rounded-full ${allOk ? "bg-green-400" : "bg-red-400 animate-pulse"}`} />
          <span>
            {allOk ? "All systems operational" : `${errorCount} service${errorCount > 1 ? "s" : ""} degraded`}
          </span>
          {services.map((s) => (
            <span key={s.name} className="flex items-center gap-1">
              <span className={`w-1 h-1 rounded-full ${s.status === "ok" ? "bg-green-400" : "bg-red-400"}`} />
              <span className={s.status === "ok" ? "text-cyber-dim" : "text-red-400"}>{s.name}</span>
            </span>
          ))}
        </div>
        <div className="flex items-center gap-3">
          {lastCheck && <span className="text-cyber-dim">Checked: {lastCheck.toLocaleTimeString()}</span>}
          <span className="text-cyber-dim">{expanded ? "▼" : "▲"} Details</span>
        </div>
      </div>

      {/* Expanded detail panel */}
      {expanded && (
        <div className="bg-cyber-bg/98 border-t border-cyber-border p-4 max-h-60 overflow-y-auto">
          <div className="flex justify-between items-center mb-3">
            <h4 className="text-xs font-bold text-white">System Transparency Panel</h4>
            <button onClick={checkServices} className="text-[10px] text-cyber-accent hover:underline">
              Refresh Now
            </button>
          </div>
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-cyber-border/50">
                <th className="text-left py-1 text-cyber-muted font-normal">Service</th>
                <th className="text-left py-1 text-cyber-muted font-normal">Status</th>
                <th className="text-left py-1 text-cyber-muted font-normal">Detail</th>
                <th className="text-right py-1 text-cyber-muted font-normal">Latency</th>
              </tr>
            </thead>
            <tbody>
              {services.map((s) => (
                <tr key={s.name} className="border-b border-cyber-border/20">
                  <td className="py-1.5 font-mono text-white">{s.name}</td>
                  <td className="py-1.5">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      s.status === "ok" ? "bg-green-500/15 text-green-400" : "bg-red-500/15 text-red-400"
                    }`}>
                      {s.status === "ok" ? "OK" : "ERROR"}
                    </span>
                  </td>
                  <td className="py-1.5 text-cyber-dim">{s.detail || "—"}</td>
                  <td className="py-1.5 text-right font-mono text-cyber-dim">{s.latency ? `${s.latency}ms` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 text-[10px] text-cyber-dim font-mono">
            Data sources: yfinance (daily OHLCV) | MT5 FTMO-Demo (live account) | Local exports (backtest results)
            <br />
            Signal engine: TA-Lib + 1-bar execution delay | Backtest engine: vectorbt 0.28.1
            <br />
            All signals use .shift(1) to prevent lookahead bias | Fees: 0.05% per trade
          </div>
        </div>
      )}
    </div>
  );
}
