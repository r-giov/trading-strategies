"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import StatCard from "@/components/StatCard";

/* ── Types ── */
interface AuditStep {
  step: string;
  status: string;
  detail?: string;
}

interface BacktestResult {
  equity_curve: { dates: string[]; values: number[] };
  metrics: Record<string, number | null>;
  is_metrics: Record<string, number | null>;
  oos_metrics: Record<string, number | null>;
  trade_log: Array<Record<string, unknown>>;
  params: Record<string, number>;
  ticker: string;
  strategy: string;
  split_date: string;
  data_points: number;
  start_date: string;
  train_ratio: number;
  status?: string;
  error?: string;
  audit?: {
    steps?: AuditStep[];
    data_source?: string;
    download_time?: string;
    [key: string]: unknown;
  };
}

/* ── Strategy configs ── */
const STRATEGY_CONFIGS: Record<string, { params: Record<string, number>; description: string }> = {
  MACD_Crossover: {
    params: { fast_period: 12, slow_period: 26, signal_period: 9 },
    description: "MACD line crosses signal line — classic momentum",
  },
  Donchian_Breakout: {
    params: { entry_period: 20, exit_period: 10, filter_period: 50 },
    description: "Price breaks Donchian channel with SMA trend filter",
  },
  EMA_Crossover: {
    params: { fast_ema: 12, slow_ema: 26, trend_filter: 200 },
    description: "Fast/slow EMA crossover with trend confirmation",
  },
  Supertrend: {
    params: { atr_period: 14, multiplier: 3.0 },
    description: "ATR-based trend following with dynamic stops",
  },
  RSI_Mean_Reversion: {
    params: { rsi_len: 14, oversold: 30, overbought: 70 },
    description: "Buy oversold, sell overbought — works in ranging markets",
  },
  Triple_EMA: {
    params: { ema1_period: 8, ema2_period: 21, ema3_period: 55 },
    description: "Three EMA crossover ensemble — any cross triggers",
  },
  Schaff_Trend_Cycle: {
    params: { fast_period: 23, slow_period: 50, cycle_period: 10 },
    description: "Stochastic of MACD — cyclical trend detection",
  },
};

const STRATEGIES = Object.entries(STRATEGY_CONFIGS).map(([value, cfg]) => ({
  value,
  label: value.replace(/_/g, " "),
  description: cfg.description,
  paramKeys: Object.keys(cfg.params),
}));

/* ── Ticker groups ── */
const TICKER_GROUPS: Record<string, string[]> = {
  "FTMO Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOT-USD", "LINK-USD", "AVAX-USD", "DOGE-USD"],
  "FTMO Indices": ["^DJI", "^GSPC", "^IXIC", "^GDAXI", "^FTSE"],
  "FTMO Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCAD=X"],
  "US Large Cap": ["AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "MA"],
  Commodities: ["GC=F", "CL=F", "SI=F"],
  ETFs: ["SPY", "QQQ", "IWM", "GLD", "TLT", "XLE", "XLV", "XLF"],
};

const ALL_TICKERS = Object.values(TICKER_GROUPS).flat();

/* ── Data sources ── */
const DATA_SOURCES = [
  { value: "yfinance", label: "yfinance", enabled: true },
  { value: "alpaca", label: "Alpaca", enabled: true },
  { value: "databento", label: "Databento (coming soon)", enabled: false },
];

/* ── Helpers ── */
function fmtPct(v: number | null | undefined): string {
  if (v == null) return "\u2014";
  return `${(v * 100).toFixed(2)}%`;
}

function fmtNum(v: number | null | undefined, decimals = 3): string {
  if (v == null) return "\u2014";
  return v.toFixed(decimals);
}

/* ── Equity Curve Canvas ── */
function EquityCurveCanvas({
  curve,
  splitDate,
}: {
  curve: BacktestResult["equity_curve"];
  splitDate: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !curve.dates.length) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = rect.height;

    ctx.fillStyle = "#0d0d1a";
    ctx.fillRect(0, 0, W, H);

    const vals = curve.values;
    const minY = Math.min(...vals) * 0.98;
    const maxY = Math.max(...vals) * 1.02;
    const n = vals.length;

    const padL = 60, padR = 20, padT = 25, padB = 40;
    const toX = (i: number) => padL + (i / (n - 1)) * (W - padL - padR);
    const toY = (v: number) => padT + ((maxY - v) / (maxY - minY)) * (H - padT - padB);

    // Grid lines
    ctx.strokeStyle = "#1a1a2e";
    ctx.lineWidth = 0.5;
    for (let i = 0; i < 6; i++) {
      const y = padT + (i / 5) * (H - padT - padB);
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(W - padR, y);
      ctx.stroke();
      const val = maxY - (i / 5) * (maxY - minY);
      ctx.fillStyle = "#4a4a6a";
      ctx.font = "11px monospace";
      ctx.textAlign = "right";
      ctx.fillText(`$${(val / 1000).toFixed(0)}k`, padL - 8, y + 4);
    }

    // Date labels
    ctx.fillStyle = "#4a4a6a";
    ctx.font = "10px monospace";
    ctx.textAlign = "center";
    const dateStep = Math.max(1, Math.floor(n / 6));
    for (let i = 0; i < n; i += dateStep) {
      const x = toX(i);
      const d = curve.dates[i];
      ctx.fillText(d.slice(0, 7), x, H - 8);
    }

    // Find split index
    const splitIdx = curve.dates.findIndex((d) => d >= splitDate);

    // IS portion (blue)
    if (splitIdx > 0) {
      ctx.strokeStyle = "#00d4ff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      for (let i = 0; i <= splitIdx && i < n; i++) {
        i === 0 ? ctx.moveTo(toX(i), toY(vals[i])) : ctx.lineTo(toX(i), toY(vals[i]));
      }
      ctx.stroke();

      // Gradient fill under IS
      const gradient = ctx.createLinearGradient(0, padT, 0, H - padB);
      gradient.addColorStop(0, "rgba(0, 212, 255, 0.08)");
      gradient.addColorStop(1, "rgba(0, 212, 255, 0)");
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.moveTo(toX(0), H - padB);
      for (let i = 0; i <= splitIdx && i < n; i++) {
        ctx.lineTo(toX(i), toY(vals[i]));
      }
      ctx.lineTo(toX(Math.min(splitIdx, n - 1)), H - padB);
      ctx.closePath();
      ctx.fill();
    }

    // OOS portion (purple)
    ctx.strokeStyle = "#6c5ce7";
    ctx.lineWidth = 2;
    ctx.beginPath();
    const start = Math.max(splitIdx, 0);
    for (let i = start; i < n; i++) {
      i === start ? ctx.moveTo(toX(i), toY(vals[i])) : ctx.lineTo(toX(i), toY(vals[i]));
    }
    ctx.stroke();

    // Gradient fill under OOS
    const oosGrad = ctx.createLinearGradient(0, padT, 0, H - padB);
    oosGrad.addColorStop(0, "rgba(108, 92, 231, 0.08)");
    oosGrad.addColorStop(1, "rgba(108, 92, 231, 0)");
    ctx.fillStyle = oosGrad;
    ctx.beginPath();
    ctx.moveTo(toX(start), H - padB);
    for (let i = start; i < n; i++) {
      ctx.lineTo(toX(i), toY(vals[i]));
    }
    ctx.lineTo(toX(n - 1), H - padB);
    ctx.closePath();
    ctx.fill();

    // Split line
    if (splitIdx > 0) {
      ctx.setLineDash([5, 5]);
      ctx.strokeStyle = "#f1c40f";
      ctx.lineWidth = 1;
      const x = toX(splitIdx);
      ctx.beginPath();
      ctx.moveTo(x, padT);
      ctx.lineTo(x, H - padB);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#f1c40f";
      ctx.font = "bold 11px monospace";
      ctx.textAlign = "center";
      ctx.fillText("IS | OOS", x, padT - 6);
    }

    // Start balance line
    ctx.setLineDash([2, 4]);
    ctx.strokeStyle = "#2a2a4a";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, toY(100000));
    ctx.lineTo(W - padR, toY(100000));
    ctx.stroke();
    ctx.setLineDash([]);
  }, [curve, splitDate]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: "100%", height: 420 }}
      className="rounded-lg"
    />
  );
}

/* ── Ticker Dropdown ── */
function TickerSelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    if (!q) return TICKER_GROUPS;
    const out: Record<string, string[]> = {};
    for (const [group, tickers] of Object.entries(TICKER_GROUPS)) {
      const match = tickers.filter((t) => t.toLowerCase().includes(q));
      if (match.length) out[group] = match;
    }
    return out;
  }, [search]);

  const hasResults = Object.keys(filtered).length > 0;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white font-mono text-left flex items-center justify-between focus:border-cyber-accent focus:outline-none hover:border-cyber-accent/50 transition-colors"
      >
        <span>{value}</span>
        <svg
          className={`w-4 h-4 text-cyber-muted transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full max-h-80 overflow-auto bg-cyber-bg border border-cyber-border rounded-lg shadow-xl">
          <div className="sticky top-0 bg-cyber-bg p-2 border-b border-cyber-border">
            <input
              autoFocus
              placeholder="Search tickers..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-cyber-surface border border-cyber-border rounded px-2.5 py-1.5 text-sm text-white font-mono focus:border-cyber-accent focus:outline-none placeholder:text-cyber-dim"
            />
          </div>
          {hasResults ? (
            Object.entries(filtered).map(([group, tickers]) => (
              <div key={group}>
                <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-cyber-accent font-bold bg-cyber-surface/50 sticky top-[52px]">
                  {group}
                </div>
                {tickers.map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => {
                      onChange(t);
                      setOpen(false);
                      setSearch("");
                    }}
                    className={`w-full text-left px-4 py-1.5 text-sm font-mono hover:bg-cyber-accent/10 transition-colors ${
                      t === value ? "text-cyber-accent bg-cyber-accent/5" : "text-cyber-text"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            ))
          ) : (
            <div className="px-4 py-3 text-sm text-cyber-dim">No tickers match &ldquo;{search}&rdquo;</div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Audit Trail ── */
function AuditTrail({ result }: { result: BacktestResult }) {
  const [expanded, setExpanded] = useState(false);
  const audit = result.audit;
  const steps = audit?.steps;

  return (
    <div className="bg-cyber-surface border border-cyber-border rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-5 py-3.5 text-left hover:bg-cyber-accent/5 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-cyber-accent text-lg">&#9776;</span>
          <span className="text-sm font-bold text-white">Audit Trail &amp; Transparency</span>
          <span className="text-[10px] text-cyber-dim font-mono ml-2">
            {steps ? `${steps.length} steps` : "backtest metadata"}
          </span>
        </div>
        <svg
          className={`w-4 h-4 text-cyber-muted transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="border-t border-cyber-border px-5 py-4 space-y-4">
          {/* Metadata bar */}
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-[11px] font-mono text-cyber-dim">
            <span>Data: {audit?.data_source || "yfinance"} {result.ticker} from {result.start_date}</span>
            <span>Bars: {result.data_points}</span>
            <span>Split: {(result.train_ratio * 100).toFixed(0)}% IS at {result.split_date}</span>
            <span>Fees: 0.05%</span>
            <span>Engine: vectorbt + TA-Lib</span>
            {audit?.download_time && <span>Downloaded: {String(audit.download_time)}</span>}
          </div>

          {/* Params */}
          <div>
            <div className="text-[10px] uppercase tracking-wider text-cyber-muted mb-1.5">Parameters</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(result.params).map(([k, v]) => (
                <span
                  key={k}
                  className="bg-cyber-bg border border-cyber-border rounded px-2.5 py-1 text-[11px] font-mono text-cyber-text"
                >
                  {k.replace(/_/g, " ")}: <span className="text-cyber-accent">{v}</span>
                </span>
              ))}
            </div>
          </div>

          {/* Step timeline */}
          {steps && steps.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-cyber-muted mb-2">Signal Computation Steps</div>
              <div className="space-y-0">
                {steps.map((s, i) => (
                  <div key={i} className="flex items-start gap-3 py-1.5">
                    <div className="flex flex-col items-center">
                      <span
                        className={`w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-bold ${
                          s.status === "done" || s.status === "ok"
                            ? "bg-green-500/20 text-green-400"
                            : s.status === "warn"
                            ? "bg-yellow-500/20 text-yellow-400"
                            : "bg-cyber-border text-cyber-dim"
                        }`}
                      >
                        {s.status === "done" || s.status === "ok" ? "\u2713" : s.status === "warn" ? "!" : (i + 1)}
                      </span>
                      {i < steps.length - 1 && <div className="w-px h-4 bg-cyber-border" />}
                    </div>
                    <div>
                      <div className="text-[12px] text-cyber-text">{s.step}</div>
                      {s.detail && <div className="text-[10px] text-cyber-dim">{s.detail}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!steps && (
            <div className="text-[11px] text-cyber-dim italic">
              Detailed audit steps will appear here once the backend provides them.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Trade Log Table ── */
function TradeLogTable({ trades }: { trades: Array<Record<string, unknown>> }) {
  const [expanded, setExpanded] = useState(false);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState(true);

  if (!trades.length) return null;

  const columns = Object.keys(trades[0]);

  const sorted = useMemo(() => {
    if (!sortKey) return trades;
    return [...trades].sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === "number" && typeof vb === "number") return sortAsc ? va - vb : vb - va;
      return sortAsc
        ? String(va).localeCompare(String(vb))
        : String(vb).localeCompare(String(va));
    });
  }, [trades, sortKey, sortAsc]);

  const handleSort = (col: string) => {
    if (sortKey === col) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(col);
      setSortAsc(true);
    }
  };

  const displayTrades = expanded ? sorted : sorted.slice(0, 10);

  return (
    <div className="bg-cyber-surface border border-cyber-border rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3.5">
        <h3 className="text-sm font-bold text-white">
          Trade Log
          <span className="text-cyber-dim font-normal ml-2 text-[11px]">({trades.length} trades)</span>
        </h3>
        {trades.length > 10 && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-[11px] text-cyber-accent hover:text-white transition-colors font-mono"
          >
            {expanded ? "Show less" : `Show all ${trades.length}`}
          </button>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-t border-b border-cyber-border/50 bg-cyber-bg/50">
              {columns.map((col) => (
                <th
                  key={col}
                  onClick={() => handleSort(col)}
                  className="text-left px-3 py-2 text-[10px] text-cyber-muted uppercase tracking-wider cursor-pointer hover:text-cyber-accent transition-colors whitespace-nowrap select-none"
                >
                  {col.replace(/_/g, " ")}
                  {sortKey === col && (
                    <span className="ml-1">{sortAsc ? "\u25B2" : "\u25BC"}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayTrades.map((trade, i) => (
              <tr
                key={i}
                className="border-b border-cyber-border/20 hover:bg-cyber-accent/5 transition-colors"
              >
                {columns.map((col) => {
                  const val = trade[col];
                  const isNum = typeof val === "number";
                  const isPnl = col.toLowerCase().includes("pnl") || col.toLowerCase().includes("return") || col.toLowerCase().includes("profit");
                  const numVal = isNum ? val : null;
                  return (
                    <td
                      key={col}
                      className={`px-3 py-1.5 font-mono whitespace-nowrap ${
                        isPnl && numVal !== null
                          ? numVal >= 0
                            ? "text-green-400"
                            : "text-red-400"
                          : "text-cyber-text"
                      }`}
                    >
                      {isNum ? (Math.abs(val) < 1 ? val.toFixed(4) : val.toFixed(2)) : String(val ?? "\u2014")}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════ */
/*  MAIN PAGE                                      */
/* ══════════════════════════════════════════════ */
export default function BacktestPage() {
  const [strategy, setStrategy] = useState("MACD_Crossover");
  const [ticker, setTicker] = useState("BTC-USD");
  const [startDate, setStartDate] = useState("2018-01-01");
  const [dataSource, setDataSource] = useState("yfinance");
  const [params, setParams] = useState<Record<string, number>>({ ...STRATEGY_CONFIGS.MACD_Crossover.params });
  const [initCash, setInitCash] = useState(100000);
  const [fees, setFees] = useState(0.0005);
  const [trainRatio, setTrainRatio] = useState(0.6);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Try to fetch tickers from API (fallback to hardcoded)
  useEffect(() => {
    fetch("/api/data/tickers")
      .then((r) => {
        if (!r.ok) throw new Error("not available");
        return r.json();
      })
      .then(() => {
        // When endpoint is ready, could update TICKER_GROUPS here
      })
      .catch(() => {
        // Endpoint not available yet, using hardcoded defaults
      });
  }, []);

  const currentConfig = STRATEGY_CONFIGS[strategy];

  const handleStrategyChange = (newStrat: string) => {
    setStrategy(newStrat);
    setParams({ ...STRATEGY_CONFIGS[newStrat].params });
  };

  const runBacktest = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy,
          ticker,
          start_date: startDate,
          params,
          init_cash: initCash,
          fees,
          train_ratio: trainRatio,
          data_source: dataSource,
        }),
      });
      const data = await res.json();
      if (data.status === "error" || data.error) {
        throw new Error(data.error || "Backtest failed");
      }
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setLoading(false);
    }
  };

  const m = result?.metrics;
  const ism = result?.is_metrics;
  const oosm = result?.oos_metrics;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-extrabold text-white tracking-tight">Backtester</h1>
        <p className="text-[12px] text-cyber-muted mt-1">
          Run strategy backtests with IS/OOS validation. Same signal logic as your notebooks.
        </p>
      </div>

      {/* ── Config Panel ── */}
      <div className="bg-cyber-surface border border-cyber-border rounded-xl p-5 space-y-5">
        {/* Row 1: Strategy + Ticker + Data Source */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Strategy */}
          <div>
            <label className="text-[11px] text-cyber-muted uppercase tracking-wider block mb-1.5">
              Strategy
            </label>
            <select
              value={strategy}
              onChange={(e) => handleStrategyChange(e.target.value)}
              className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-cyber-accent focus:outline-none hover:border-cyber-accent/50 transition-colors"
            >
              {STRATEGIES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
            {currentConfig && (
              <p className="text-[10px] text-cyber-dim mt-1.5 leading-relaxed">
                {currentConfig.description}
              </p>
            )}
          </div>

          {/* Ticker */}
          <div>
            <label className="text-[11px] text-cyber-muted uppercase tracking-wider block mb-1.5">
              Ticker
            </label>
            <TickerSelector value={ticker} onChange={setTicker} />
          </div>

          {/* Data Source */}
          <div>
            <label className="text-[11px] text-cyber-muted uppercase tracking-wider block mb-1.5">
              Data Source
            </label>
            <select
              value={dataSource}
              onChange={(e) => setDataSource(e.target.value)}
              className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-cyber-accent focus:outline-none hover:border-cyber-accent/50 transition-colors"
            >
              {DATA_SOURCES.map((ds) => (
                <option key={ds.value} value={ds.value} disabled={!ds.enabled}>
                  {ds.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Row 2: Date, Cash, Fees, Split */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {/* Start Date */}
          <div>
            <label className="text-[11px] text-cyber-muted uppercase tracking-wider block mb-1.5">
              Start Date
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-cyber-accent focus:outline-none"
            />
          </div>

          {/* Initial Cash */}
          <div>
            <label className="text-[11px] text-cyber-muted uppercase tracking-wider block mb-1.5">
              Initial Cash
            </label>
            <input
              type="number"
              value={initCash}
              onChange={(e) => setInitCash(parseInt(e.target.value) || 100000)}
              className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-cyber-accent focus:outline-none"
            />
          </div>

          {/* Fees */}
          <div>
            <label className="text-[11px] text-cyber-muted uppercase tracking-wider block mb-1.5">
              Fees (bps)
            </label>
            <input
              type="number"
              step="0.0001"
              value={fees}
              onChange={(e) => setFees(parseFloat(e.target.value) || 0.0005)}
              className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-cyber-accent focus:outline-none"
            />
          </div>

          {/* IS/OOS Split */}
          <div>
            <label className="text-[11px] text-cyber-muted uppercase tracking-wider block mb-1.5">
              IS/OOS Split{" "}
              <span className="text-cyber-accent">
                {(trainRatio * 100).toFixed(0)}%
              </span>{" "}
              /{" "}
              <span className="text-cyber-purple">
                {((1 - trainRatio) * 100).toFixed(0)}%
              </span>
            </label>
            <input
              type="range"
              min={0.4}
              max={0.8}
              step={0.05}
              value={trainRatio}
              onChange={(e) => setTrainRatio(parseFloat(e.target.value))}
              className="w-full accent-cyber-accent mt-2"
            />
          </div>
        </div>

        {/* Row 3: Strategy Parameters + Run Button */}
        <div className="border-t border-cyber-border/50 pt-4">
          <div className="text-[10px] text-cyber-muted uppercase tracking-wider mb-2.5">
            Strategy Parameters
          </div>
          <div className="flex gap-4 flex-wrap items-end">
            {Object.keys(currentConfig?.params || {}).map((p) => (
              <div key={p}>
                <label className="text-[11px] text-cyber-dim block mb-1">
                  {p.replace(/_/g, " ")}
                </label>
                <input
                  type="number"
                  step="any"
                  value={params[p] ?? ""}
                  onChange={(e) =>
                    setParams({ ...params, [p]: parseFloat(e.target.value) })
                  }
                  className="w-28 bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-cyber-accent focus:outline-none"
                />
              </div>
            ))}

            <div className="ml-auto">
              <button
                onClick={runBacktest}
                disabled={loading}
                className={`px-8 py-2.5 rounded-lg text-sm font-bold transition-all ${
                  loading
                    ? "bg-cyber-border text-cyber-muted cursor-wait"
                    : "bg-cyber-accent text-cyber-bg hover:shadow-glow hover:brightness-110 cursor-pointer"
                }`}
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <span className="inline-block w-4 h-4 border-2 border-cyber-muted border-t-transparent rounded-full animate-spin" />
                    Running...
                  </span>
                ) : (
                  "Run Backtest"
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-sm text-red-400 flex items-center gap-2">
          <span className="text-red-500 text-lg">&#9888;</span>
          {error}
        </div>
      )}

      {/* ── Results ── */}
      {result && m && (
        <div className="space-y-6">
          {/* Result header */}
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <h2 className="text-lg font-bold text-white">
              {result.strategy.replace(/_/g, " ")}
              <span className="text-cyber-accent ml-2">{result.ticker}</span>
            </h2>
            <span className="text-[11px] text-cyber-dim font-mono">
              {result.data_points} bars | split {result.split_date}
            </span>
          </div>

          {/* Metrics Cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard
              label="Sharpe"
              value={fmtNum(m.sharpe)}
              color={m.sharpe && m.sharpe > 0 ? "#2ecc71" : "#e74c3c"}
            />
            <StatCard
              label="Total Return"
              value={fmtPct(m.total_return)}
              sub={m.total_return_pct != null ? `${m.total_return_pct.toFixed(1)}%` : undefined}
              color={m.total_return && m.total_return > 0 ? "#2ecc71" : "#e74c3c"}
            />
            <StatCard
              label="Max Drawdown"
              value={fmtPct(m.max_drawdown)}
              sub={m.max_drawdown_pct != null ? `${m.max_drawdown_pct.toFixed(1)}%` : undefined}
              color="#e74c3c"
            />
            <StatCard
              label="Win Rate"
              value={m.win_rate != null ? `${m.win_rate.toFixed(1)}%` : "\u2014"}
              color={m.win_rate && m.win_rate > 50 ? "#2ecc71" : "#f1c40f"}
            />
            <StatCard
              label="Profit Factor"
              value={fmtNum(m.profit_factor, 2)}
              color={m.profit_factor && m.profit_factor > 1 ? "#2ecc71" : "#e74c3c"}
            />
            <StatCard label="Trades" value={m.total_trades ?? "\u2014"} />
          </div>

          {/* IS vs OOS Comparison */}
          {ism && oosm && (
            <div className="bg-cyber-surface border border-cyber-border rounded-xl overflow-hidden">
              <div className="px-5 py-3.5 border-b border-cyber-border/50">
                <h3 className="text-sm font-bold text-white">In-Sample vs Out-of-Sample</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="border-b border-cyber-border/50 bg-cyber-bg/30">
                      <th className="text-left px-4 py-2.5 text-[10px] text-cyber-muted uppercase tracking-wider">
                        Metric
                      </th>
                      <th className="text-left px-4 py-2.5 text-[10px] text-cyber-accent uppercase tracking-wider">
                        In-Sample
                      </th>
                      <th className="text-left px-4 py-2.5 text-[10px] text-cyber-purple uppercase tracking-wider">
                        Out-of-Sample
                      </th>
                      <th className="text-left px-4 py-2.5 text-[10px] text-cyber-muted uppercase tracking-wider">
                        Degradation
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {["sharpe", "total_return", "max_drawdown", "win_rate", "profit_factor", "total_trades"].map(
                      (metric) => {
                        const isVal = ism[metric];
                        const oosVal = oosm[metric];
                        const deg =
                          isVal != null && oosVal != null && isVal !== 0
                            ? ((oosVal - isVal) / Math.abs(isVal)) * 100
                            : null;
                        const isReturnLike =
                          metric.includes("return") || metric.includes("drawdown");
                        const isWinRate = metric === "win_rate";

                        const formatVal = (v: number | null) => {
                          if (v == null) return "\u2014";
                          if (isReturnLike) return fmtPct(v);
                          if (isWinRate) return `${v.toFixed(1)}%`;
                          if (metric === "total_trades") return String(Math.round(v));
                          return v.toFixed(3);
                        };

                        return (
                          <tr key={metric} className="border-b border-cyber-border/20 hover:bg-cyber-accent/5 transition-colors">
                            <td className="px-4 py-2.5 text-cyber-muted capitalize font-medium">
                              {metric.replace(/_/g, " ")}
                            </td>
                            <td className="px-4 py-2.5 font-mono text-cyber-accent">
                              {formatVal(isVal)}
                            </td>
                            <td className="px-4 py-2.5 font-mono text-cyber-purple">
                              {formatVal(oosVal)}
                            </td>
                            <td
                              className="px-4 py-2.5 font-mono"
                              style={{
                                color:
                                  deg !== null
                                    ? deg > -20
                                      ? "#2ecc71"
                                      : "#e74c3c"
                                    : "#6a6a8a",
                              }}
                            >
                              {deg !== null
                                ? `${deg > 0 ? "+" : ""}${deg.toFixed(1)}%`
                                : "\u2014"}
                            </td>
                          </tr>
                        );
                      }
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Equity Curve */}
          <div className="bg-cyber-surface border border-cyber-border rounded-xl overflow-hidden">
            <div className="px-5 py-3.5 border-b border-cyber-border/50 flex items-center justify-between">
              <h3 className="text-sm font-bold text-white">Equity Curve</h3>
              <div className="flex gap-4 text-[11px]">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-3 h-0.5 bg-cyber-accent rounded" />
                  <span className="text-cyber-accent">In-Sample</span>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-3 h-0.5 bg-cyber-purple rounded" />
                  <span className="text-cyber-purple">Out-of-Sample</span>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-3 h-0.5 bg-[#f1c40f] rounded" />
                  <span className="text-[#f1c40f]">Split</span>
                </span>
              </div>
            </div>
            <div className="p-4">
              <EquityCurveCanvas curve={result.equity_curve} splitDate={result.split_date} />
            </div>
          </div>

          {/* Trade Log */}
          {result.trade_log && result.trade_log.length > 0 && (
            <TradeLogTable trades={result.trade_log} />
          )}

          {/* Audit Trail */}
          <AuditTrail result={result} />
        </div>
      )}
    </div>
  );
}
