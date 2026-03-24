"use client";

import { useEffect, useState } from "react";
import { getStrategies } from "@/lib/api";
import StatCard from "@/components/StatCard";

interface StrategyExport {
  strategy: string;
  ticker: string;
  summary: Record<string, any>;
}

// Normalize the two export formats into one shape
function normalize(s: StrategyExport) {
  const d = s.summary;
  // Portfolio format: full_sample.sharpe, out_of_sample.sharpe
  // Single format: metrics_full_sample.sharpe, metrics_in_sample.sharpe
  const fs = d.full_sample || d.metrics_full_sample || {};
  const oos = d.out_of_sample || d.metrics_out_of_sample || {};
  const is_ = d.in_sample || d.metrics_in_sample || {};
  const meta = d.metadata || {};
  const mc = d.monte_carlo || d.monte_carlo_ftmo || {};
  const params = d.best_params || {};

  return {
    strategy: s.strategy,
    ticker: s.ticker,
    name: meta.strategy_name || d.strategy || s.strategy,
    tickerDisplay: meta.ticker || s.ticker,
    startDate: meta.start_date || "",
    endDate: meta.end_date || "",
    splitDate: meta.train_end || "",
    sharpe: fs.sharpe ?? fs.sharpe_ratio ?? null,
    totalReturn: fs.total_return ?? null,
    annReturn: fs.ann_return ?? fs.annualized_return ?? null,
    maxDD: fs.max_dd ?? fs.max_drawdown ?? null,
    winRate: fs.win_rate ?? null,
    profitFactor: fs.pf ?? fs.profit_factor ?? null,
    trades: fs.trades ?? fs.total_trades ?? null,
    tradesPerYear: fs.trades_yr ?? fs.trades_per_year ?? null,
    sortino: fs.sortino ?? fs.sortino_ratio ?? null,
    calmar: fs.calmar ?? fs.calmar_ratio ?? null,
    volatility: fs.volatility ?? fs.ann_vol ?? null,
    oosSharpe: oos.sharpe ?? oos.sharpe_ratio ?? null,
    isSharpe: is_.sharpe ?? is_.sharpe_ratio ?? null,
    passRate: mc.pass_rate_pct ?? mc.pass_rate ?? null,
    params,
  };
}

const CATEGORIES: Record<string, { label: string; desc: string; color: string }> = {
  Portfolio: { label: "Portfolio Strategies", desc: "Multi-asset ensemble strategies with dynamic allocation", color: "#00d4ff" },
  Trend: { label: "Trend Following", desc: "MACD, EMA, Supertrend — ride momentum, cut losers", color: "#2ecc71" },
  Breakout: { label: "Breakout", desc: "Donchian channel breakouts with trend confirmation", color: "#f1c40f" },
  Rotation: { label: "Rotation / Momentum", desc: "KAMA rotation, momentum scoring, periodic rebalancing", color: "#6c5ce7" },
  "Mean Reversion": { label: "Mean Reversion", desc: "RSI, Bollinger — fade extremes in ranging markets", color: "#e67e22" },
};

function categorize(strategy: string, ticker: string): string {
  const s = strategy.toLowerCase();
  if (ticker.toLowerCase() === "portfolio" || s.includes("portfolio") || s.includes("ensemble") || s.includes("crypto_portfolio")) return "Portfolio";
  if (s.includes("kama") || s.includes("rotation") || s.includes("momentum")) return "Rotation";
  if (s.includes("donchian") || s.includes("breakout") || s.includes("atr_volatility")) return "Breakout";
  if (s.includes("rsi") || s.includes("bollinger") || s.includes("mean_rev")) return "Mean Reversion";
  return "Trend";
}

function fmtPct(v: number | null): string {
  if (v == null) return "—";
  // If value is already in decimal form (< 5), multiply by 100
  if (Math.abs(v) < 5) return `${(v * 100).toFixed(2)}%`;
  return `${v.toFixed(2)}%`;
}

function fmtColor(v: number | null, invert = false): string {
  if (v == null) return "#6a6a8a";
  return (invert ? v < 0 : v > 0) ? "#2ecc71" : "#e74c3c";
}

function getTier(n: ReturnType<typeof normalize>): { label: string; color: string } {
  if (n.passRate && n.passRate >= 25) return { label: "FTMO READY", color: "#2ecc71" };
  if (n.oosSharpe && n.oosSharpe > 0.7) return { label: "STRONG", color: "#00d4ff" };
  if (n.oosSharpe && n.oosSharpe > 0) return { label: "VIABLE", color: "#f1c40f" };
  if (n.sharpe && n.sharpe > 1) return { label: "STRONG", color: "#00d4ff" };
  return { label: "RESEARCH", color: "#6a6a8a" };
}

export default function StrategiesPage() {
  const [raw, setRaw] = useState<StrategyExport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"recent" | "sharpe" | "return">("recent");
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    getStrategies()
      .then((d) => setRaw(d as any))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const strategies = raw.map(normalize);

  const grouped: Record<string, ReturnType<typeof normalize>[]> = {};
  strategies.forEach((s) => {
    const cat = categorize(s.strategy, s.ticker);
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(s);
  });

  const sortFn = (a: ReturnType<typeof normalize>, b: ReturnType<typeof normalize>) => {
    if (sortBy === "sharpe") return (b.sharpe ?? 0) - (a.sharpe ?? 0);
    if (sortBy === "return") return (b.totalReturn ?? 0) - (a.totalReturn ?? 0);
    return 0;
  };

  const filtered = activeCategory ? { [activeCategory]: grouped[activeCategory] || [] } : grouped;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-4xl animate-pulse text-cyber-accent">&#9670;</div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight">Strategy Library</h1>
          <p className="text-[12px] text-cyber-muted mt-1">
            {strategies.length} strategy-ticker pairs across {Object.keys(grouped).length} categories
          </p>
        </div>
        <div className="flex gap-2">
          {(["recent", "sharpe", "return"] as const).map((s) => (
            <button key={s} onClick={() => setSortBy(s)}
              className={`text-[11px] px-3 py-1.5 rounded-lg font-medium transition-all ${
                sortBy === s ? "bg-cyber-accent/15 text-cyber-accent border border-cyber-accent/30"
                  : "text-cyber-muted hover:text-cyber-text bg-cyber-surface border border-cyber-border"
              }`}>{s === "recent" ? "Recent" : s === "sharpe" ? "Sharpe" : "Return"}</button>
          ))}
        </div>
      </div>

      {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 mb-6 text-sm text-red-400">{error}</div>}

      {/* Category pills */}
      <div className="flex gap-2 mb-6 flex-wrap">
        <button onClick={() => setActiveCategory(null)}
          className={`text-[12px] px-4 py-2 rounded-lg font-semibold transition-all ${
            !activeCategory ? "bg-white/10 text-white border border-white/20"
              : "text-cyber-muted hover:text-cyber-text bg-cyber-surface border border-cyber-border"
          }`}>All ({strategies.length})</button>
        {Object.entries(CATEGORIES).map(([key, cat]) => {
          const count = grouped[key]?.length || 0;
          if (count === 0) return null;
          return (
            <button key={key} onClick={() => setActiveCategory(activeCategory === key ? null : key)}
              className={`text-[12px] px-4 py-2 rounded-lg font-semibold transition-all ${
                activeCategory === key ? "border" : "text-cyber-muted hover:text-cyber-text bg-cyber-surface border border-cyber-border"
              }`}
              style={activeCategory === key ? { backgroundColor: `${cat.color}15`, color: cat.color, borderColor: `${cat.color}40` } : undefined}
            >{cat.label} ({count})</button>
          );
        })}
      </div>

      {/* Strategy cards by category */}
      {Object.entries(filtered).map(([catKey, strats]) => {
        if (!strats || strats.length === 0) return null;
        const cat = CATEGORIES[catKey] || { label: catKey, desc: "", color: "#6a6a8a" };
        const sorted = [...strats].sort(sortFn);

        return (
          <div key={catKey} className="mb-8">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-1 h-6 rounded-full" style={{ backgroundColor: cat.color }} />
              <div>
                <h2 className="text-base font-bold text-white">{cat.label}</h2>
                <p className="text-[11px] text-cyber-dim">{cat.desc}</p>
              </div>
              <span className="text-[11px] text-cyber-muted bg-cyber-surface px-2 py-0.5 rounded-full ml-auto">
                {sorted.length} {sorted.length === 1 ? "strategy" : "strategies"}
              </span>
            </div>

            <div className="flex flex-col gap-4">
              {sorted.map((n, i) => {
                const tier = getTier(n);
                const paramStr = Object.entries(n.params).map(([k, v]) => `${k.replace(/_/g, " ")}=${v}`).join(", ");
                const cardKey = `${n.strategy}/${n.ticker}`;
                const isExpanded = expanded === cardKey;
                const meta = raw.find(r => r.strategy === n.strategy && r.ticker === n.ticker)?.summary?.metadata;
                const mc = raw.find(r => r.strategy === n.strategy && r.ticker === n.ticker)?.summary;
                const components = mc?.components;

                return (
                  <div key={i}
                    className={`bg-cyber-surface border rounded-xl transition-all cursor-pointer ${
                      isExpanded ? "border-cyber-accent/40 shadow-glow" : "border-cyber-border hover:border-cyber-accent/20 hover:shadow-glow"
                    }`}
                    onClick={() => setExpanded(isExpanded ? null : cardKey)}
                  >
                    {/* Card Header — always visible */}
                    <div className="p-5">
                      <div className="flex justify-between items-start mb-4">
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-lg font-bold text-white">{n.name.replace(/_/g, " ")}</span>
                            <span className="text-sm text-cyber-accent font-mono">{n.tickerDisplay}</span>
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full"
                              style={{ color: tier.color, backgroundColor: `${tier.color}15`, border: `1px solid ${tier.color}30` }}>
                              {tier.label}
                            </span>
                            <span className={`text-[10px] text-cyber-dim transition-transform ${isExpanded ? "rotate-180" : ""}`}>
                              &#9660;
                            </span>
                          </div>
                          {paramStr && <div className="text-[11px] text-cyber-dim mt-1 font-mono">{paramStr}</div>}
                        </div>
                        {n.startDate && (
                          <div className="text-[11px] text-cyber-dim text-right">
                            {n.startDate} → {n.endDate}
                            {n.splitDate && <><br />IS/OOS split: {n.splitDate}</>}
                          </div>
                        )}
                      </div>

                      <div className="flex gap-3 flex-wrap">
                        <StatCard label="Sharpe" value={n.sharpe?.toFixed(3) ?? "—"} color={fmtColor(n.sharpe)} />
                        <StatCard label="Return" value={fmtPct(n.totalReturn)} color={fmtColor(n.totalReturn)} />
                        <StatCard label="Max DD" value={fmtPct(n.maxDD)} color="#e74c3c" />
                        {n.winRate != null && (
                          <StatCard label="Win Rate" value={`${n.winRate > 1 ? n.winRate.toFixed(1) : (n.winRate * 100).toFixed(1)}%`}
                            color={fmtColor((n.winRate > 1 ? n.winRate : n.winRate * 100) - 50)} />
                        )}
                        {n.profitFactor != null && (
                          <StatCard label="Profit Factor" value={n.profitFactor.toFixed(2)} color={fmtColor(n.profitFactor - 1)} />
                        )}
                        {n.trades != null && (
                          <StatCard label="Trades" value={n.trades} sub={n.tradesPerYear ? `${n.tradesPerYear.toFixed(1)}/yr` : undefined} />
                        )}
                        <StatCard label="OOS Sharpe" value={n.oosSharpe?.toFixed(3) ?? "—"} color={fmtColor(n.oosSharpe)}
                          sub={n.isSharpe ? `IS: ${n.isSharpe.toFixed(3)}` : undefined} />
                        {n.passRate != null && (
                          <StatCard label="FTMO Pass" value={`${n.passRate.toFixed(1)}%`}
                            color={n.passRate >= 25 ? "#2ecc71" : n.passRate >= 10 ? "#f1c40f" : "#e74c3c"} />
                        )}
                      </div>
                    </div>

                    {/* Expanded Detail Panel */}
                    {isExpanded && (
                      <div className="border-t border-cyber-border/50 p-5 bg-cyber-bg/50" onClick={(e) => e.stopPropagation()}>
                        {/* Action Buttons */}
                        <div className="flex gap-3 mb-4">
                          <a href={`/backtest?strategy=${encodeURIComponent(n.strategy)}&ticker=${encodeURIComponent(n.tickerDisplay)}`}
                            className="bg-cyber-accent/10 text-cyber-accent border border-cyber-accent/30 px-4 py-2 rounded-lg text-xs font-semibold hover:bg-cyber-accent/20 transition-all hover:shadow-glow">
                            Run Backtest
                          </a>
                          <a href={`/ftmo`}
                            className="bg-cyber-purple/10 text-cyber-purple border border-cyber-purple/30 px-4 py-2 rounded-lg text-xs font-semibold hover:bg-cyber-purple/20 transition-all">
                            Monte Carlo
                          </a>
                          <a href={`/research`}
                            className="bg-white/5 text-cyber-text border border-cyber-border px-4 py-2 rounded-lg text-xs font-semibold hover:bg-white/10 transition-all">
                            Research with AI
                          </a>
                        </div>

                        {/* Additional Metrics */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                          {n.calmar != null && <StatCard label="Calmar" value={n.calmar.toFixed(3)} color={fmtColor(n.calmar)} />}
                          {n.sortino != null && <StatCard label="Sortino" value={n.sortino.toFixed(3)} color={fmtColor(n.sortino)} />}
                          {n.volatility != null && <StatCard label="Volatility" value={fmtPct(n.volatility)} />}
                          {n.annReturn != null && <StatCard label="Ann. Return" value={fmtPct(n.annReturn)} color={fmtColor(n.annReturn)} />}
                        </div>

                        {/* Portfolio Components (if portfolio strategy) */}
                        {components && Array.isArray(components) && components.length > 0 && (
                          <div className="mb-4">
                            <h4 className="text-[11px] text-cyber-muted uppercase tracking-wider mb-2 font-semibold">Portfolio Components</h4>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                              {components.map((comp: any, ci: number) => (
                                <div key={ci} className="bg-cyber-surface border border-cyber-border/50 rounded-lg px-3 py-2 text-[12px]">
                                  <div className="flex justify-between">
                                    <span className="text-cyber-accent font-mono font-semibold">{comp.ticker || comp.symbol}</span>
                                    <span className="text-cyber-muted">{comp.strategy?.replace(/_/g, " ")}</span>
                                  </div>
                                  <div className="flex gap-4 mt-1 text-[11px] text-cyber-dim">
                                    {comp.weight != null && <span>Weight: {(comp.weight * 100).toFixed(0)}%</span>}
                                    {comp.sharpe != null && <span>Sharpe: {comp.sharpe.toFixed(2)}</span>}
                                    {comp.total_return != null && <span>Return: {(comp.total_return * 100).toFixed(1)}%</span>}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Metadata footer */}
                        {meta && (
                          <div className="text-[10px] text-cyber-dim font-mono bg-cyber-bg rounded-lg px-3 py-2">
                            {meta.data_source && <span>Source: {meta.data_source} | </span>}
                            {meta.total_bars && <span>{meta.total_bars} bars | </span>}
                            {meta.total_years && <span>{meta.total_years.toFixed(1)} years | </span>}
                            {meta.grid_combos_tested && <span>{meta.grid_combos_tested.toLocaleString()} grid combos tested | </span>}
                            {meta.environment && <span>Env: {meta.environment} | </span>}
                            {meta.export_date_human && <span>Exported: {meta.export_date_human}</span>}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
