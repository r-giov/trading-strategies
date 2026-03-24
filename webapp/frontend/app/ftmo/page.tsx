"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { getPortfolioConfig, getStrategies } from "@/lib/api";
import type { PortfolioConfig, StrategySummary } from "@/lib/types";
import StatCard from "@/components/StatCard";
import RiskGauge from "@/components/RiskGauge";

interface MCResult {
  n_passed: number;
  n_blown_total: number;
  n_blown_daily: number;
  n_still_trading: number;
  n_sims: number;
  pass_rate: number;
  blow_rate: number;
  median_days_to_pass: number | null;
  avg_days_to_pass: number | null;
  max_days: number;
  chart_days: number;
  paths: number[][];
  verdict: string;
  rules: {
    account: number;
    profit_target_pct: number;
    max_daily_loss_pct: number;
    max_total_loss_pct: number;
    time_limit: string;
  };
}

function MonteCarloChart({ mc }: { mc: MCResult }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !mc.paths.length) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width, H = canvas.height;
    ctx.fillStyle = "#0d0d1a";
    ctx.fillRect(0, 0, W, H);

    const allVals = mc.paths.flat();
    const minY = Math.min(...allVals) * 0.98;
    const maxY = Math.max(...allVals) * 1.02;
    const days = (mc.chart_days || 90) + 1;

    const toX = (d: number) => 50 + (d / (days - 1)) * (W - 70);
    const toY = (v: number) => H - 30 - ((v - minY) / (maxY - minY)) * (H - 50);

    // Grid
    ctx.strokeStyle = "#1a1a2e";
    ctx.lineWidth = 0.5;
    for (let i = 0; i < 5; i++) {
      const y = 20 + (i / 4) * (H - 50);
      ctx.beginPath(); ctx.moveTo(50, y); ctx.lineTo(W - 20, y); ctx.stroke();
      const val = maxY - (i / 4) * (maxY - minY);
      ctx.fillStyle = "#4a4a6a";
      ctx.font = "10px monospace";
      ctx.fillText(`$${(val / 1000).toFixed(0)}k`, 5, y + 4);
    }

    // Paths
    mc.paths.forEach((path, i) => {
      const final = path[path.length - 1];
      const passed = (final - 100000) / 100000 >= 0.10;
      const blown = (final - 100000) / 100000 <= -0.10;
      ctx.strokeStyle = passed ? "rgba(46,204,113,0.4)" : blown ? "rgba(231,76,60,0.25)" : "rgba(100,100,140,0.08)";
      ctx.lineWidth = passed ? 1.2 : 0.6;
      ctx.beginPath();
      path.forEach((v, d) => {
        d === 0 ? ctx.moveTo(toX(d), toY(v)) : ctx.lineTo(toX(d), toY(v));
      });
      ctx.stroke();
    });

    // FTMO lines
    const target = 110000;
    const loss = 90000;
    ctx.setLineDash([6, 4]);
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#2ecc71";
    ctx.beginPath(); ctx.moveTo(50, toY(target)); ctx.lineTo(W - 20, toY(target)); ctx.stroke();
    ctx.strokeStyle = "#e74c3c";
    ctx.beginPath(); ctx.moveTo(50, toY(loss)); ctx.lineTo(W - 20, toY(loss)); ctx.stroke();
    ctx.setLineDash([]);

    // Labels
    ctx.fillStyle = "#2ecc71"; ctx.font = "bold 11px monospace";
    ctx.fillText(`Target $110k`, W - 110, toY(target) - 6);
    ctx.fillStyle = "#e74c3c";
    ctx.fillText(`Max Loss $90k`, W - 115, toY(loss) + 14);

  }, [mc]);

  return <canvas ref={canvasRef} width={800} height={380} className="w-full rounded-lg" />;
}

const VERDICT_STYLES: Record<string, { bg: string; border: string; color: string }> = {
  FAVORABLE: { bg: "rgba(46,204,113,0.1)", border: "#2ecc71", color: "#2ecc71" },
  POSSIBLE: { bg: "rgba(241,196,15,0.1)", border: "#f1c40f", color: "#f1c40f" },
  CHALLENGING: { bg: "rgba(230,126,34,0.1)", border: "#e67e22", color: "#e67e22" },
  UNLIKELY: { bg: "rgba(231,76,60,0.1)", border: "#e74c3c", color: "#e74c3c" },
};

interface MT5Account {
  connected: boolean;
  account?: { login: number; balance: number; equity: number; profit: number };
  ftmo_status?: {
    profit_progress: number; profit_target: number; profit_pct: number;
    daily_pnl: number; daily_limit: number; daily_pct: number;
    total_pnl: number; total_limit: number; total_pct: number;
  };
  positions?: Array<Record<string, unknown>>;
  recent_trades?: Array<Record<string, unknown>>;
}

export default function FTMOPage() {
  const [config, setConfig] = useState<PortfolioConfig | null>(null);
  const [strategies, setStrategies] = useState<StrategySummary[]>([]);
  const [mcResults, setMcResults] = useState<Record<string, MCResult>>({});
  const [running, setRunning] = useState<string | null>(null);
  const [mt5, setMt5] = useState<MT5Account | null>(null);
  const [activeStrategies, setActiveStrategies] = useState<boolean[]>([]);

  // Portfolio strategies beyond the crypto components
  const portfolioStrategies = [
    { id: "3EMA_ENSEMBLE", symbol: "PORTFOLIO", strategy: "3EMA Ensemble", sector: "Tech/Growth", oos_sharpe: 1.09, ftmo_pass_rate: 30.8, weight: 1, universe: "IXIC, META, GOOG, NFLX, TSLA, AAPL, AMZN, NVDA" },
    { id: "MACD_PORTFOLIO", symbol: "PORTFOLIO", strategy: "MACD Portfolio", sector: "Healthcare/Defensive", oos_sharpe: 1.11, ftmo_pass_rate: 14.7, weight: 1, universe: "JNJ, LLY, MRK, ABBV, WMT" },
    { id: "DONCHIAN_PORTFOLIO", symbol: "PORTFOLIO", strategy: "Donchian Breakout", sector: "Energy/Value/Industrials", oos_sharpe: 1.16, ftmo_pass_rate: 22.9, weight: 1, universe: "XOM, CVX, COP, JPM, GS, CAT, DE, HON" },
    { id: "SUPERTREND_PORTFOLIO", symbol: "PORTFOLIO", strategy: "Supertrend", sector: "Indices/Blue Chips", oos_sharpe: 0.36, ftmo_pass_rate: 7.5, weight: 1, universe: "DJI, SPX, DAX, FTSE, MSFT, V, MA, COST" },
  ];

  useEffect(() => {
    getPortfolioConfig().then((cfg) => {
      setConfig(cfg);
      // Initialize all strategies as armed (crypto components + portfolio strategies)
      setActiveStrategies(new Array(cfg.components.length + 4).fill(true));
    }).catch(console.error);
    getStrategies().then(setStrategies).catch(console.error);
    fetch("/api/mt5/account").then(r => r.json()).then(setMt5).catch(console.error);
    // Refresh MT5 every 30s
    const interval = setInterval(() => {
      fetch("/api/mt5/account").then(r => r.json()).then(setMt5).catch(console.error);
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const runMC = useCallback(async (strategy: string, ticker: string) => {
    const key = `${strategy}/${ticker}`;
    setRunning(key);
    try {
      const res = await fetch(`/api/montecarlo/from-exports/${strategy}/${ticker}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setMcResults((prev) => ({ ...prev, [key]: data }));
    } catch (err) {
      console.error("MC failed:", err);
    } finally {
      setRunning(null);
    }
  }, []);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-extrabold text-white tracking-tight">FTMO Challenge</h1>
        <p className="text-[12px] text-cyber-muted mt-1">
          Account monitoring, risk limits & Monte Carlo simulation
        </p>
      </div>

      {/* Account Overview */}
      {config && (
        <>
          {/* Live MT5 Connection Status */}
          {mt5 && (
            <div className={`flex items-center gap-2 mb-4 px-3 py-1.5 rounded-lg text-[11px] font-mono w-fit ${
              mt5.connected ? "bg-green-500/10 text-green-400 border border-green-500/20" : "bg-red-500/10 text-red-400 border border-red-500/20"
            }`}>
              <span className={`w-2 h-2 rounded-full ${mt5.connected ? "bg-green-400 animate-pulse" : "bg-red-400"}`} />
              {mt5.connected ? `MT5 Connected — Account #${mt5.account?.login}` : "MT5 Disconnected"}
              {mt5.connected && <span className="text-cyber-dim ml-2">auto-refresh 30s</span>}
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <StatCard
              label="Equity"
              value={mt5?.account ? `$${mt5.account.equity.toLocaleString(undefined, {minimumFractionDigits: 2})}` : `$${(config.account_size / 1000).toFixed(0)}K`}
              sub={mt5?.account ? `Balance: $${mt5.account.balance.toLocaleString()}` : "Connect MT5"}
              color="#00d4ff"
            />
            <StatCard
              label="Profit Progress"
              value={mt5?.ftmo_status ? `$${mt5.ftmo_status.profit_progress.toLocaleString(undefined, {minimumFractionDigits: 2})}` : "$0"}
              sub={`Target: $${config.profit_target.toLocaleString()}`}
              color={mt5?.ftmo_status && mt5.ftmo_status.profit_progress > 0 ? "#2ecc71" : "#e74c3c"}
            />
            <StatCard
              label="Open Positions"
              value={mt5?.positions?.length ?? 0}
              sub={mt5?.account ? `P&L: $${mt5.account.profit.toFixed(2)}` : "—"}
              color={mt5?.positions?.length ? "#00d4ff" : "#6a6a8a"}
            />
            <StatCard
              label="Recent Trades"
              value={mt5?.recent_trades?.length ?? 0}
              sub="Last 7 days"
            />
          </div>

          <div className="bg-cyber-surface border border-cyber-border rounded-xl p-5 mb-6">
            <h3 className="text-sm font-bold text-white mb-4">Live Risk Status</h3>
            <div className="flex gap-6 flex-wrap">
              <RiskGauge
                label="Profit Progress"
                current={mt5?.ftmo_status?.profit_progress ?? 0}
                max={config.profit_target}
                color="#2ecc71"
              />
              <RiskGauge
                label="Daily Loss Used"
                current={Math.abs(mt5?.ftmo_status?.daily_pnl ?? 0)}
                max={config.max_daily_loss}
                color={(mt5?.ftmo_status?.daily_pnl ?? 0) < -config.max_daily_loss * 0.5 ? "#e74c3c" : "#f1c40f"}
              />
              <RiskGauge
                label="Total Loss Used"
                current={Math.abs(Math.min(mt5?.ftmo_status?.total_pnl ?? 0, 0))}
                max={config.max_total_loss}
                color={(mt5?.ftmo_status?.total_pnl ?? 0) < -config.max_total_loss * 0.5 ? "#e74c3c" : "#e74c3c"}
              />
            </div>
          </div>

          {/* Active Trading Strategies — Toggle Panel */}
          <div className="terminal-panel p-5 mb-6">
            <div className="terminal-header mb-4">ACTIVE_STRATEGIES</div>
            <div className="flex items-center justify-between mb-3">
              <div className="text-[10px] text-cyber-dim">
                {activeStrategies.filter(Boolean).length}/{config.components.length + portfolioStrategies.length} strategies armed
                {" // "}Click toggles to arm/disarm
              </div>
              <div className="flex gap-2">
                <button onClick={() => setActiveStrategies(config.components.map(() => true))}
                  className="text-[9px] text-[#00ff88] tracking-wider hover:neon-green">[ARM_ALL]</button>
                <button onClick={() => setActiveStrategies(config.components.map(() => false))}
                  className="text-[9px] text-[#ff2255] tracking-wider hover:neon-red">[DISARM_ALL]</button>
              </div>
            </div>
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-cyber-border/50">
                  <th className="text-left px-3 py-2 text-cyber-muted">STATUS</th>
                  <th className="text-left px-3 py-2 text-cyber-muted">COMPONENT</th>
                  <th className="text-left px-3 py-2 text-cyber-muted">SYMBOL</th>
                  <th className="text-left px-3 py-2 text-cyber-muted">STRATEGY</th>
                  <th className="text-left px-3 py-2 text-cyber-muted">WEIGHT</th>
                  <th className="text-left px-3 py-2 text-cyber-muted">OOS_SHARPE</th>
                  <th className="text-left px-3 py-2 text-cyber-muted">FTMO_PASS</th>
                </tr>
              </thead>
              <tbody>
                {/* Section: Portfolio Strategies */}
                <tr><td colSpan={7} className="px-3 pt-3 pb-1 text-[9px] text-cyber-accent tracking-[3px]">&gt;&gt;PORTFOLIO_STRATEGIES</td></tr>
                {portfolioStrategies.map((ps, idx) => {
                  const globalIdx = config.components.length + idx;
                  const armed = activeStrategies[globalIdx] ?? true;
                  return (
                    <tr key={ps.id}
                      className={`border-b border-cyber-border/20 cursor-pointer transition-all ${
                        armed ? "hover:bg-green-500/5" : "hover:bg-red-500/5 opacity-50"
                      }`}
                      onClick={() => {
                        const next = [...activeStrategies];
                        next[globalIdx] = !next[globalIdx];
                        setActiveStrategies(next);
                      }}
                    >
                      <td className="px-3 py-2.5">
                        <div className={`w-8 h-4 rounded-full flex items-center px-0.5 transition-all ${
                          armed ? "bg-[#00ff88]/20 border border-[#00ff88]/40" : "bg-cyber-border border border-cyber-border"
                        }`}>
                          <div className={`w-3 h-3 rounded-full transition-all ${
                            armed ? "bg-[#00ff88] translate-x-3.5 shadow-glow-green" : "bg-cyber-dim translate-x-0"
                          }`} />
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-[10px] text-cyber-dim">{ps.id}</td>
                      <td className="px-3 py-2.5 font-semibold text-cyber-purple">{ps.sector}</td>
                      <td className="px-3 py-2.5 text-cyber-text">{ps.strategy}</td>
                      <td className="px-3 py-2.5 text-[9px] text-cyber-dim">{ps.universe}</td>
                      <td className="px-3 py-2.5" style={{ color: ps.oos_sharpe > 0.5 ? "#00ff88" : "#ffaa00" }}>
                        {ps.oos_sharpe.toFixed(3)}
                      </td>
                      <td className="px-3 py-2.5" style={{ color: ps.ftmo_pass_rate >= 25 ? "#00ff88" : ps.ftmo_pass_rate >= 10 ? "#ffaa00" : "#ff2255" }}>
                        {ps.ftmo_pass_rate.toFixed(1)}%
                      </td>
                    </tr>
                  );
                })}

                {/* Section: Crypto Components */}
                <tr><td colSpan={7} className="px-3 pt-4 pb-1 text-[9px] text-cyber-accent tracking-[3px]">&gt;&gt;CRYPTO_COMPONENTS</td></tr>
                {config.components.map((comp, idx) => {
                  const armed = activeStrategies[idx] ?? true;
                  return (
                    <tr key={comp.id}
                      className={`border-b border-cyber-border/20 cursor-pointer transition-all ${
                        armed ? "hover:bg-green-500/5" : "hover:bg-red-500/5 opacity-50"
                      }`}
                      onClick={() => {
                        const next = [...activeStrategies];
                        next[idx] = !next[idx];
                        setActiveStrategies(next);
                      }}
                    >
                      <td className="px-3 py-2.5">
                        <div className={`w-8 h-4 rounded-full flex items-center px-0.5 transition-all ${
                          armed ? "bg-[#00ff88]/20 border border-[#00ff88]/40" : "bg-cyber-border border border-cyber-border"
                        }`}>
                          <div className={`w-3 h-3 rounded-full transition-all ${
                            armed ? "bg-[#00ff88] translate-x-3.5 shadow-glow-green" : "bg-cyber-dim translate-x-0"
                          }`} />
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-[10px] text-cyber-dim">{comp.id}</td>
                      <td className="px-3 py-2.5 font-semibold text-cyber-accent">{comp.symbol}</td>
                      <td className="px-3 py-2.5 text-cyber-text">{comp.strategy.replace(/_/g, " ")}</td>
                      <td className="px-3 py-2.5 text-white">{(comp.weight * 100).toFixed(1)}%</td>
                      <td className="px-3 py-2.5" style={{ color: comp.oos_sharpe && comp.oos_sharpe > 0.5 ? "#00ff88" : "#ffaa00" }}>
                        {comp.oos_sharpe?.toFixed(3) ?? "—"}
                      </td>
                      <td className="px-3 py-2.5" style={{ color: (comp.ftmo_pass_rate ?? 0) >= 40 ? "#00ff88" : "#ffaa00" }}>
                        {comp.ftmo_pass_rate ? `${comp.ftmo_pass_rate.toFixed(1)}%` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Monte Carlo Simulator */}
      <div className="mb-6">
        <h2 className="text-base font-bold text-white mb-1">Monte Carlo Simulator</h2>
        <p className="text-[11px] text-cyber-muted mb-4">
          Bootstraps 5,000 equity paths from observed daily returns. Rules: 10% profit target, 5% max daily loss, 10% max total loss, <strong className="text-cyber-accent">no time limit</strong>.
          Each sim runs until pass or blow — matching current FTMO rules.
        </p>

        {strategies.length === 0 ? (
          <div className="bg-cyber-surface border border-cyber-border rounded-xl p-8 text-center">
            <p className="text-cyber-muted text-sm">No strategy exports found. Run a notebook to generate daily returns.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            {strategies.map((s) => {
              const key = `${s.strategy}/${s.ticker}`;
              const mc = mcResults[key];
              const vs = mc ? VERDICT_STYLES[mc.verdict] || VERDICT_STYLES.UNLIKELY : null;

              return (
                <div key={key} className="bg-cyber-surface border border-cyber-border rounded-xl p-5">
                  <div className="flex justify-between items-center mb-4">
                    <div>
                      <span className="text-base font-bold text-white">
                        {(s.summary?.metadata?.strategy_name || s.strategy).replace(/_/g, " ")}
                      </span>
                      <span className="text-sm text-cyber-accent font-mono ml-2">
                        {s.summary?.metadata?.ticker || s.ticker}
                      </span>
                    </div>
                    <button
                      onClick={() => runMC(s.strategy, s.ticker)}
                      disabled={running === key}
                      className={`text-xs font-semibold px-5 py-2 rounded-lg transition-all ${
                        running === key
                          ? "bg-cyber-border text-cyber-muted cursor-wait"
                          : "bg-cyber-purple text-white hover:shadow-glow-purple cursor-pointer"
                      }`}
                    >
                      {running === key ? "Simulating..." : mc ? "Re-run" : "Run Simulation"}
                    </button>
                  </div>

                  {mc && (
                    <>
                      <div className="flex gap-3 flex-wrap mb-4">
                        <StatCard
                          label="Pass Rate"
                          value={`${mc.pass_rate.toFixed(1)}%`}
                          color={mc.pass_rate >= 50 ? "#2ecc71" : mc.pass_rate >= 25 ? "#f1c40f" : mc.pass_rate >= 10 ? "#e67e22" : "#e74c3c"}
                        />
                        <StatCard label="Passed" value={mc.n_passed.toLocaleString()} sub={`of ${mc.n_sims.toLocaleString()}`} color="#2ecc71" />
                        <StatCard label="Blown (Total)" value={mc.n_blown_total.toLocaleString()} color="#e74c3c" />
                        <StatCard label="Blown (Daily)" value={mc.n_blown_daily.toLocaleString()} color="#e67e22" />
                        {mc.median_days_to_pass && (
                          <StatCard label="Median Days to Pass" value={Math.round(mc.median_days_to_pass)} sub={`avg: ${Math.round(mc.avg_days_to_pass || 0)}`} color="#00d4ff" />
                        )}
                        <StatCard label="Still Trading" value={mc.n_still_trading.toLocaleString()} sub={`after ${mc.max_days} days`} color="#6a6a8a" />
                      </div>

                      {vs && (
                        <div
                          className="flex items-center px-4 py-2.5 rounded-lg mb-4"
                          style={{ backgroundColor: vs.bg, border: `1px solid ${vs.border}` }}
                        >
                          <span className="text-sm font-bold mr-3" style={{ color: vs.color }}>{mc.verdict}</span>
                          <span className="text-[12px] text-cyber-muted">
                            {mc.pass_rate.toFixed(1)}% of simulations hit the 10% profit target within 30 days
                          </span>
                        </div>
                      )}

                      <MonteCarloChart mc={mc} />

                      {/* Transparency: show data source */}
                      <div className="mt-3 px-3 py-2 bg-cyber-bg rounded-lg text-[10px] text-cyber-dim font-mono">
                        Source: exports/{s.strategy}/{s.ticker}/daily_returns.csv
                        &nbsp;|&nbsp; {mc.n_sims.toLocaleString()} bootstrap samples
                        &nbsp;|&nbsp; FTMO rules: $100K, 10% target, 5% daily / 10% total loss, 30 days
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
