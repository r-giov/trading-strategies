"use client";

import { useEffect, useState, useCallback } from "react";
import StatCard from "@/components/StatCard";
import SignalCard from "@/components/SignalCard";
import PortfolioTable from "@/components/PortfolioTable";
import RiskGauge from "@/components/RiskGauge";
import PipelineView from "@/components/PipelineView";
import { getSignals, getPortfolioConfig } from "@/lib/api";
import type { PortfolioSignals, PortfolioConfig } from "@/lib/types";

export default function DashboardPage() {
  const [signals, setSignals] = useState<PortfolioSignals | null>(null);
  const [config, setConfig] = useState<PortfolioConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [signalFilter, setSignalFilter] = useState<"ALL" | "BUY" | "SELL" | "HOLD">("ALL");

  const filteredSignals = signals
    ? signalFilter === "ALL"
      ? signals.components
      : signals.components.filter((s) => s.action === signalFilter)
    : [];

  const fetchData = useCallback(async (refresh = false) => {
    try {
      setError(null);
      const [sig, cfg] = await Promise.all([
        getSignals(refresh),
        config ? Promise.resolve(config) : getPortfolioConfig(),
      ]);
      setSignals(sig);
      if (!config) setConfig(cfg);
      setLastRefresh(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch data");
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => fetchData(), 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Derived stats
  const activePositions = signals
    ? Object.values(signals.aggregated).filter((a) => a.action === "BUY").length
    : 0;
  const avgSharpe = config
    ? config.components.reduce((sum, c) => sum + (c.oos_sharpe || 0), 0) / config.components.filter(c => c.oos_sharpe).length
    : 0;
  const avgPassRate = config
    ? config.components.reduce((sum, c) => sum + (c.ftmo_pass_rate || 0), 0) / config.components.length
    : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center animate-flicker">
          <div className="text-[10px] text-cyber-accent tracking-[4px] mb-2">&gt;&gt;INITIALIZING</div>
          <div className="text-cyber-muted text-[11px]">Loading signal engine...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-5 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex justify-between items-center mb-5">
        <div>
          <div className="text-[9px] text-cyber-accent tracking-[4px] mb-1">&gt;&gt;LIVE_FEED</div>
          <h1 className="text-xl font-bold text-white neon-text">
            SIGNAL_DASHBOARD
          </h1>
          <p className="text-[10px] text-cyber-dim mt-1 tracking-wider">
            {lastRefresh ? `LAST_UPDATE: ${lastRefresh.toLocaleTimeString()}` : ""}
            {" // "}REFRESH: 60s
          </p>
        </div>
        <button
          onClick={() => { setLoading(true); fetchData(true); }}
          className="terminal-panel px-4 py-2 text-[10px] text-cyber-accent tracking-[2px] hover:shadow-glow transition-all"
        >
          [REFRESH_SIGNALS]
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 mb-6 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          label="Account"
          value={config ? `$${(config.account_size / 1000).toFixed(0)}K` : "—"}
          sub="FTMO Challenge"
          color="#00d4ff"
        />
        <StatCard
          label="Portfolio Sharpe"
          value={avgSharpe.toFixed(3)}
          sub="Weighted OOS avg"
          color={avgSharpe > 0.5 ? "#2ecc71" : "#f1c40f"}
        />
        <StatCard
          label="Active Positions"
          value={activePositions}
          sub={`of ${config?.symbols.length || 0} symbols`}
          color={activePositions > 0 ? "#2ecc71" : "#6a6a8a"}
        />
        <StatCard
          label="Avg Pass Rate"
          value={`${avgPassRate.toFixed(1)}%`}
          sub="FTMO Monte Carlo"
          color={avgPassRate >= 40 ? "#2ecc71" : avgPassRate >= 25 ? "#f1c40f" : "#e74c3c"}
        />
      </div>

      {/* FTMO Risk Gauges */}
      {config && (
        <div className="terminal-panel p-5 mb-5">
          <div className="terminal-header mb-3">FTMO_RISK_LIMITS</div>
          <div className="flex gap-6 flex-wrap">
            <RiskGauge
              label="Profit Target"
              current={0}
              max={config.profit_target}
              color="#2ecc71"
            />
            <RiskGauge
              label="Daily Loss Limit"
              current={0}
              max={config.max_daily_loss}
              color="#f1c40f"
            />
            <RiskGauge
              label="Total Loss Limit"
              current={0}
              max={config.max_total_loss}
              color="#e74c3c"
            />
          </div>
        </div>
      )}

      {/* Component Signals */}
      {signals && (
        <>
          <div className="mb-5">
            <div className="flex items-center justify-between mb-3">
              <div className="text-[9px] text-cyber-accent tracking-[3px]">&gt;&gt;COMPONENT_SIGNALS ({filteredSignals.length}/{signals.components.length})</div>
              <div className="flex gap-1">
                {(["ALL", "BUY", "SELL", "HOLD"] as const).map((f) => {
                  const count = f === "ALL" ? signals.components.length : signals.components.filter(s => s.action === f).length;
                  return (
                    <button
                      key={f}
                      onClick={() => setSignalFilter(f)}
                      className={`text-[9px] px-2.5 py-1 rounded tracking-[1px] transition-all ${
                        signalFilter === f
                          ? f === "BUY" ? "bg-[#00ff88]/15 text-[#00ff88] border border-[#00ff88]/30"
                          : f === "SELL" ? "bg-[#ff2255]/15 text-[#ff2255] border border-[#ff2255]/30"
                          : "bg-cyber-accent/15 text-cyber-accent border border-cyber-accent/30"
                          : "text-cyber-dim border border-cyber-border hover:text-cyber-muted"
                      }`}
                    >
                      {f} {count > 0 && `(${count})`}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredSignals.map((sig) => (
                <SignalCard key={sig.component_id} signal={sig} />
              ))}
            </div>
          </div>

          <PortfolioTable aggregated={signals.aggregated} />

          {/* Pipeline Visualization */}
          <div className="mt-5">
            <PipelineView />
          </div>
        </>
      )}
    </div>
  );
}
