"use client";

import { useEffect, useState } from "react";

interface PipelineStage {
  id: string;
  label: string;
  status: "active" | "idle" | "error" | "disabled";
  detail: string;
  sub?: string;
}

interface SignalData {
  components: Array<{
    component_id: string;
    symbol: string;
    strategy: string;
    action: string;
    reason: string;
    last_close?: number;
  }>;
  aggregated: Record<string, { action: string; weight: number; summary: string }>;
  timestamp: string | null;
}

interface MT5Data {
  connected: boolean;
  account?: { equity: number; balance: number; profit: number; login: number };
  positions?: Array<{ symbol: string; type: string; volume: number; profit: number }>;
}

export default function PipelineView() {
  const [signals, setSignals] = useState<SignalData | null>(null);
  const [mt5, setMt5] = useState<MT5Data | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch("/api/signals/portfolio").then(r => r.json()).catch(() => null),
      fetch("/api/mt5/account").then(r => r.json()).catch(() => null),
    ]).then(([sig, mt]) => {
      setSignals(sig);
      setMt5(mt);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="terminal-panel p-5">
        <div className="terminal-header mb-3">TRADING_PIPELINE</div>
        <div className="text-[10px] text-cyber-dim animate-pulse">Loading pipeline state...</div>
      </div>
    );
  }

  const nComponents = signals?.components?.length ?? 0;
  const nBuy = signals?.components?.filter(c => c.action === "BUY").length ?? 0;
  const nSell = signals?.components?.filter(c => c.action === "SELL").length ?? 0;
  const nHold = signals?.components?.filter(c => c.action === "HOLD").length ?? 0;
  const aggBuys = signals ? Object.values(signals.aggregated).filter(a => a.action === "BUY") : [];
  const mt5Connected = mt5?.connected ?? false;
  const openPositions = mt5?.positions?.length ?? 0;
  const equity = mt5?.account?.equity ?? 100000;

  const stages: PipelineStage[] = [
    {
      id: "data",
      label: "DATA_FEED",
      status: signals ? "active" : "error",
      detail: signals ? `yfinance // ${nComponents} instruments` : "NO DATA",
      sub: signals?.timestamp ? `Last: ${signals.timestamp.slice(11, 19)} UTC` : undefined,
    },
    {
      id: "signals",
      label: "SIGNAL_ENGINE",
      status: nComponents > 0 ? "active" : "error",
      detail: `MACD + Donchian // TA-Lib`,
      sub: `${nBuy} BUY / ${nSell} SELL / ${nHold} HOLD`,
    },
    {
      id: "aggregate",
      label: "AGGREGATOR",
      status: "active",
      detail: `${Object.keys(signals?.aggregated || {}).length} symbols aggregated`,
      sub: aggBuys.length > 0
        ? `Active: ${aggBuys.map(a => Object.entries(signals!.aggregated).find(([_, v]) => v === a)?.[0]).join(", ")}`
        : "All HOLD — no action required",
    },
    {
      id: "risk",
      label: "RISK_GUARD",
      status: mt5Connected ? "active" : "idle",
      detail: `FTMO limits: 5% daily / 10% total`,
      sub: mt5Connected ? `Equity: $${equity.toLocaleString()} // ${openPositions} positions` : "MT5 required for live risk",
    },
    {
      id: "sizing",
      label: "POSITION_SIZER",
      status: aggBuys.length > 0 ? "active" : "idle",
      detail: `Carver equal-weight (1/${nComponents})`,
      sub: aggBuys.length > 0
        ? `${aggBuys.length} tickets ready`
        : "No trades to size — all HOLD",
    },
    {
      id: "executor",
      label: "MT5_EXECUTOR",
      status: mt5Connected ? (aggBuys.length > 0 ? "active" : "idle") : "disabled",
      detail: mt5Connected ? `Account #${mt5?.account?.login} // FTMO-Demo` : "DISCONNECTED",
      sub: mt5Connected
        ? `${openPositions} open positions // P&L: $${mt5?.account?.profit?.toFixed(2) ?? "0.00"}`
        : "Start MT5 to enable execution",
    },
    {
      id: "alerts",
      label: "TELEGRAM_ALERTS",
      status: "idle",
      detail: "Configured // awaiting signal change",
      sub: "Sends on: OPEN, CLOSE, DAILY_SUMMARY",
    },
  ];

  const statusColor = (s: string) => {
    switch (s) {
      case "active": return "#00ff88";
      case "idle": return "#505070";
      case "error": return "#ff2255";
      case "disabled": return "#3a3a5a";
      default: return "#505070";
    }
  };

  const statusLabel = (s: string) => {
    switch (s) {
      case "active": return "ACTIVE";
      case "idle": return "IDLE";
      case "error": return "ERROR";
      case "disabled": return "OFF";
      default: return "?";
    }
  };

  return (
    <div className="terminal-panel p-5">
      <div className="terminal-header mb-4">TRADING_PIPELINE_VISUALIZATION</div>

      <div className="relative">
        {stages.map((stage, i) => (
          <div key={stage.id} className="flex items-stretch mb-0">
            {/* Connector line */}
            <div className="flex flex-col items-center w-8 flex-shrink-0">
              {/* Dot */}
              <div
                className="w-3 h-3 rounded-full border-2 flex-shrink-0"
                style={{
                  borderColor: statusColor(stage.status),
                  backgroundColor: stage.status === "active" ? statusColor(stage.status) : "transparent",
                  boxShadow: stage.status === "active" ? `0 0 8px ${statusColor(stage.status)}` : "none",
                }}
              />
              {/* Vertical line */}
              {i < stages.length - 1 && (
                <div className="w-px flex-1 min-h-[24px]" style={{
                  background: `linear-gradient(to bottom, ${statusColor(stage.status)}, ${statusColor(stages[i + 1].status)})`,
                  opacity: 0.4,
                }} />
              )}
            </div>

            {/* Stage content */}
            <div className={`flex-1 pb-4 pl-3 ${stage.status === "disabled" ? "opacity-40" : ""}`}>
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-[10px] font-bold tracking-[2px]" style={{ color: statusColor(stage.status) }}>
                  {stage.label}
                </span>
                <span
                  className="text-[8px] px-1.5 py-0.5 rounded tracking-wider"
                  style={{
                    color: statusColor(stage.status),
                    backgroundColor: `${statusColor(stage.status)}15`,
                    border: `1px solid ${statusColor(stage.status)}30`,
                  }}
                >
                  {statusLabel(stage.status)}
                </span>
              </div>
              <div className="text-[10px] text-cyber-text">{stage.detail}</div>
              {stage.sub && <div className="text-[9px] text-cyber-dim mt-0.5">{stage.sub}</div>}
            </div>

            {/* Data flow arrow */}
            {i < stages.length - 1 && (
              <div className="flex items-start pt-1 pr-2">
                <span className="text-[8px] text-cyber-dim">
                  {stage.status === "active" ? ">>>" : "---"}
                </span>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Signal detail strip */}
      {signals && (
        <div className="mt-3 pt-3 border-t border-cyber-border/30">
          <div className="text-[9px] text-cyber-dim tracking-[2px] mb-2">&gt;&gt;CURRENT_SIGNALS</div>
          <div className="grid grid-cols-2 gap-2">
            {signals.components.map((c) => (
              <div key={c.component_id} className="flex items-center gap-2 text-[10px]">
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{
                    backgroundColor: c.action === "BUY" ? "#00ff88" : c.action === "SELL" ? "#ff2255" : "#505070",
                    boxShadow: c.action !== "HOLD" ? `0 0 4px ${c.action === "BUY" ? "#00ff88" : "#ff2255"}` : "none",
                  }}
                />
                <span className="text-cyber-accent">{c.symbol}</span>
                <span className="text-cyber-dim">{c.strategy.replace(/_/g, " ")}</span>
                <span style={{ color: c.action === "BUY" ? "#00ff88" : c.action === "SELL" ? "#ff2255" : "#505070" }}>
                  {c.action}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pipeline transparency footer */}
      <div className="mt-3 pt-2 border-t border-cyber-border/20 text-[8px] text-cyber-dim">
        yfinance daily bars → TA-Lib indicators → 1-bar execution delay → Carver equal-weight → FTMO risk guard (80% buffer) → MT5 market orders → Telegram
      </div>
    </div>
  );
}
