import { useState, useCallback, useMemo, useRef } from "react";

const FTMO_RULES = {
  profit_target: 0.10,
  max_daily_loss: 0.05,
  max_total_loss: 0.10,
  trading_days: 30,
};

function parseCSV(text) {
  const lines = text.trim().split("\n");
  const headers = lines[0].split(",");
  return lines.slice(1).map((line) => {
    const vals = line.split(",");
    const obj = {};
    headers.forEach((h, i) => (obj[h.trim()] = vals[i]?.trim()));
    return obj;
  });
}

function runMonteCarlo(dailyReturns, n = 5000) {
  const results = [];
  const paths = [];
  const ACCOUNT = 100000;
  for (let s = 0; s < n; s++) {
    let eq = ACCOUNT;
    let dayStart = ACCOUNT;
    let passed = false, blownTotal = false, blownDaily = false;
    const path = [ACCOUNT];
    for (let d = 0; d < FTMO_RULES.trading_days; d++) {
      dayStart = eq;
      const idx = Math.floor(Math.random() * dailyReturns.length);
      eq = eq * (1 + dailyReturns[idx]);
      path.push(eq);
      if ((eq - dayStart) / ACCOUNT < -FTMO_RULES.max_daily_loss) { blownDaily = true; break; }
      if ((eq - ACCOUNT) / ACCOUNT < -FTMO_RULES.max_total_loss) { blownTotal = true; break; }
      if ((eq - ACCOUNT) / ACCOUNT >= FTMO_RULES.profit_target) { passed = true; break; }
    }
    while (path.length < FTMO_RULES.trading_days + 1) path.push(path[path.length - 1]);
    results.push({ final: eq, passed, blownTotal, blownDaily });
    if (s < 150) paths.push(path);
  }
  const nPassed = results.filter(r => r.passed).length;
  const nBlownT = results.filter(r => r.blownTotal).length;
  const nBlownD = results.filter(r => r.blownDaily).length;
  const nStill = n - nPassed - nBlownT - nBlownD;
  return { nPassed, nBlownT, nBlownD, nStill, n, paths, results, passRate: (nPassed / n * 100) };
}

function StatCard({ label, value, sub, color }) {
  return (
    <div style={{ background: "#1a1a2e", border: "1px solid #2a2a4a", borderRadius: 8, padding: "14px 18px", minWidth: 140 }}>
      <div style={{ fontSize: 11, color: "#8888aa", textTransform: "uppercase", letterSpacing: 1.2, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: color || "#e0e0ff", fontFamily: "'JetBrains Mono', monospace" }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "#6a6a8a", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function MiniBar({ value, max, color }) {
  const pct = Math.min(Math.abs(value) / max * 100, 100);
  return (
    <div style={{ width: 80, height: 8, background: "#1a1a2e", borderRadius: 4, overflow: "hidden", display: "inline-block", verticalAlign: "middle", marginLeft: 8 }}>
      <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 4 }} />
    </div>
  );
}

function MonteCarloChart({ mc }) {
  const canvasRef = useRef(null);
  const drawn = useRef(false);

  const draw = useCallback((canvas) => {
    if (!canvas || drawn.current) return;
    drawn.current = true;
    canvasRef.current = canvas;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    ctx.fillStyle = "#0d0d1a";
    ctx.fillRect(0, 0, W, H);

    const allVals = mc.paths.flat();
    const minY = Math.min(...allVals) * 0.98;
    const maxY = Math.max(...allVals) * 1.02;
    const days = FTMO_RULES.trading_days + 1;

    const toX = (d) => 50 + (d / (days - 1)) * (W - 70);
    const toY = (v) => H - 30 - ((v - minY) / (maxY - minY)) * (H - 50);

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
      const r = mc.results[i];
      ctx.strokeStyle = r.passed ? "rgba(46,204,113,0.35)" : (r.blownTotal || r.blownDaily) ? "rgba(231,76,60,0.25)" : "rgba(100,100,140,0.08)";
      ctx.lineWidth = r.passed ? 1.2 : 0.6;
      ctx.beginPath();
      path.forEach((v, d) => { d === 0 ? ctx.moveTo(toX(d), toY(v)) : ctx.lineTo(toX(d), toY(v)); });
      ctx.stroke();
    });

    // FTMO lines
    const target = 100000 * (1 + FTMO_RULES.profit_target);
    const loss = 100000 * (1 - FTMO_RULES.max_total_loss);
    ctx.setLineDash([6, 4]);
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#2ecc71"; ctx.beginPath(); ctx.moveTo(50, toY(target)); ctx.lineTo(W - 20, toY(target)); ctx.stroke();
    ctx.strokeStyle = "#e74c3c"; ctx.beginPath(); ctx.moveTo(50, toY(loss)); ctx.lineTo(W - 20, toY(loss)); ctx.stroke();
    ctx.setLineDash([]);

    // Labels
    ctx.fillStyle = "#2ecc71"; ctx.font = "bold 11px monospace";
    ctx.fillText(`Target $${(target / 1000).toFixed(0)}k`, W - 100, toY(target) - 6);
    ctx.fillStyle = "#e74c3c";
    ctx.fillText(`Max Loss $${(loss / 1000).toFixed(0)}k`, W - 110, toY(loss) + 14);
  }, [mc]);

  return <canvas ref={draw} width={700} height={340} style={{ borderRadius: 8, width: "100%" }} />;
}

export default function StrategyCommandCenter() {
  const [strategies, setStrategies] = useState([]);
  const [dailyReturnsMap, setDailyReturnsMap] = useState({});
  const [activeTab, setActiveTab] = useState("overview");
  const [mcResults, setMcResults] = useState({});
  const [mcRunning, setMcRunning] = useState(null);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    const files = Array.from(e.dataTransfer?.files || e.target?.files || []);
    files.forEach((file) => {
      const reader = new FileReader();
      reader.onload = (ev) => {
        const text = ev.target.result;
        if (file.name.endsWith("_summary.json")) {
          try {
            const data = JSON.parse(text);
            setStrategies((prev) => {
              const exists = prev.find(s => s.metadata.strategy_name === data.metadata.strategy_name && s.metadata.ticker === data.metadata.ticker);
              if (exists) return prev.map(s => (s.metadata.strategy_name === data.metadata.strategy_name && s.metadata.ticker === data.metadata.ticker) ? data : s);
              return [...prev, data];
            });
          } catch (err) { console.error("JSON parse error:", err); }
        } else if (file.name.includes("_daily_returns.csv")) {
          const rows = parseCSV(text);
          const name = file.name.split("_daily_returns")[0];
          const rets = rows.map(r => parseFloat(r.strategy_return)).filter(v => !isNaN(v));
          setDailyReturnsMap((prev) => ({ ...prev, [name]: rets }));
        }
      };
      reader.readAsText(file);
    });
  }, []);

  const handleRunMC = useCallback((key, rets) => {
    setMcRunning(key);
    setTimeout(() => {
      const result = runMonteCarlo(rets, 5000);
      setMcResults((prev) => ({ ...prev, [key]: result }));
      setMcRunning(null);
    }, 50);
  }, []);

  const correlation = useMemo(() => {
    const keys = Object.keys(dailyReturnsMap);
    if (keys.length < 2) return null;
    const minLen = Math.min(...keys.map(k => dailyReturnsMap[k].length));
    const matrix = {};
    keys.forEach(k1 => {
      matrix[k1] = {};
      keys.forEach(k2 => {
        const a = dailyReturnsMap[k1].slice(0, minLen);
        const b = dailyReturnsMap[k2].slice(0, minLen);
        const meanA = a.reduce((s, v) => s + v, 0) / a.length;
        const meanB = b.reduce((s, v) => s + v, 0) / b.length;
        let cov = 0, varA = 0, varB = 0;
        for (let i = 0; i < minLen; i++) {
          cov += (a[i] - meanA) * (b[i] - meanB);
          varA += (a[i] - meanA) ** 2;
          varB += (b[i] - meanB) ** 2;
        }
        matrix[k1][k2] = varA > 0 && varB > 0 ? cov / Math.sqrt(varA * varB) : 0;
      });
    });
    return { keys, matrix };
  }, [dailyReturnsMap]);

  const fmt = (v, d = 2) => v == null ? "—" : typeof v === "number" ? (Math.abs(v) < 10 ? v.toFixed(d) : v.toFixed(d)) : v;
  const fmtPct = (v) => v == null ? "—" : `${(v * 100).toFixed(2)}%`;
  const fmtColor = (v, invert = false) => {
    if (v == null) return "#6a6a8a";
    const good = invert ? v < 0 : v > 0;
    return good ? "#2ecc71" : "#e74c3c";
  };

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "compare", label: "Compare" },
    { id: "correlation", label: "Correlation" },
    { id: "montecarlo", label: "FTMO Monte Carlo" },
  ];

  return (
    <div style={{ background: "#0d0d1a", color: "#d0d0e8", fontFamily: "'Segoe UI', 'Helvetica Neue', sans-serif", minHeight: "100vh", padding: 0 }}>
      {/* Header */}
      <div style={{ background: "linear-gradient(135deg, #0d0d1a 0%, #1a1a3e 100%)", borderBottom: "1px solid #2a2a4a", padding: "20px 28px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, letterSpacing: -0.5, color: "#fff" }}>
              <span style={{ color: "#6c5ce7" }}>&#9670;</span> Strategy Command Center
            </h1>
            <p style={{ margin: "4px 0 0", fontSize: 12, color: "#6a6a8a" }}>
              {strategies.length} strateg{strategies.length === 1 ? "y" : "ies"} loaded &middot; {Object.keys(dailyReturnsMap).length} return series
            </p>
          </div>
          <label style={{ cursor: "pointer", background: "#6c5ce7", color: "#fff", padding: "10px 20px", borderRadius: 8, fontSize: 13, fontWeight: 600, border: "none" }}>
            + Import Files
            <input type="file" multiple accept=".json,.csv" onChange={handleDrop} style={{ display: "none" }} />
          </label>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 0, borderBottom: "1px solid #2a2a4a", background: "#111128" }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)}
            style={{ background: activeTab === t.id ? "#1a1a3e" : "transparent", color: activeTab === t.id ? "#fff" : "#6a6a8a",
              border: "none", borderBottom: activeTab === t.id ? "2px solid #6c5ce7" : "2px solid transparent",
              padding: "12px 24px", fontSize: 13, fontWeight: 600, cursor: "pointer", transition: "all 0.15s" }}>
            {t.label}
          </button>
        ))}
      </div>

      <div style={{ padding: "24px 28px" }}>
        {/* Drop Zone (shown when empty) */}
        {strategies.length === 0 && (
          <div onDragOver={(e) => e.preventDefault()} onDrop={handleDrop}
            style={{ border: "2px dashed #2a2a4a", borderRadius: 12, padding: "60px 40px", textAlign: "center",
              background: "#111128", transition: "border-color 0.2s" }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>&#128230;</div>
            <p style={{ fontSize: 16, color: "#8888aa", margin: "0 0 8px" }}>
              Drag &amp; drop your strategy export files here
            </p>
            <p style={{ fontSize: 12, color: "#5a5a7a" }}>
              Accepts: *_summary.json, *_daily_returns.csv, *_trades.csv
            </p>
            <p style={{ fontSize: 12, color: "#5a5a7a", marginTop: 16 }}>
              Or click <strong style={{ color: "#6c5ce7" }}>+ Import Files</strong> above
            </p>
          </div>
        )}

        {/* ═══ OVERVIEW TAB ═══ */}
        {activeTab === "overview" && strategies.length > 0 && (
          <div>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16, color: "#fff" }}>Strategy Summary Cards</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              {strategies.map((s, i) => {
                const m = s.metrics_full_sample;
                const p = s.best_params;
                const paramStr = Object.entries(p).map(([k, v]) => `${k.replace(/_/g, " ")}=${v}`).join(", ");
                return (
                  <div key={i} style={{ background: "#111128", border: "1px solid #2a2a4a", borderRadius: 12, padding: 20 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                      <div>
                        <span style={{ fontSize: 18, fontWeight: 700, color: "#fff" }}>{s.metadata.strategy_name}</span>
                        <span style={{ fontSize: 13, color: "#6c5ce7", marginLeft: 10 }}>{s.metadata.ticker}</span>
                        <div style={{ fontSize: 11, color: "#5a5a7a", marginTop: 2 }}>{paramStr}</div>
                      </div>
                      <div style={{ fontSize: 11, color: "#5a5a7a", textAlign: "right" }}>
                        {s.metadata.start_date} → {s.metadata.end_date}<br />
                        IS/OOS split: {s.metadata.train_end}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                      <StatCard label="Sharpe" value={fmt(m.sharpe_ratio, 3)} color={fmtColor(m.sharpe_ratio)} />
                      <StatCard label="Return" value={fmtPct(m.total_return)} color={fmtColor(m.total_return)} />
                      <StatCard label="Max DD" value={fmtPct(m.max_drawdown)} color="#e74c3c" />
                      <StatCard label="Win Rate" value={m.win_rate ? `${m.win_rate.toFixed(1)}%` : "—"} color={fmtColor((m.win_rate || 0) - 50)} />
                      <StatCard label="Profit Factor" value={fmt(m.profit_factor)} color={fmtColor((m.profit_factor || 0) - 1)} />
                      <StatCard label="Trades" value={m.total_trades} sub={`${m.trades_per_year?.toFixed(1)}/yr`} />
                      <StatCard label="Calmar" value={fmt(m.calmar_ratio)} color={fmtColor(m.calmar_ratio)} />
                      <StatCard label="OOS Sharpe" value={fmt(s.metrics_out_of_sample?.sharpe_ratio, 3)}
                        color={fmtColor(s.metrics_out_of_sample?.sharpe_ratio)} sub={`IS: ${fmt(s.metrics_in_sample?.sharpe_ratio, 3)}`} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ═══ COMPARE TAB ═══ */}
        {activeTab === "compare" && strategies.length > 0 && (
          <div>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16, color: "#fff" }}>Head-to-Head Comparison</h2>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid #2a2a4a" }}>
                    {["Strategy", "Ticker", "Sharpe", "Sortino", "Return", "Ann. Return", "Max DD", "Volatility", "Win Rate", "PF", "Trades", "OOS Sharpe", "Sharpe Δ"].map(h => (
                      <th key={h} style={{ padding: "10px 12px", textAlign: "left", color: "#8888aa", fontWeight: 600, fontSize: 11, textTransform: "uppercase", letterSpacing: 0.8 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {strategies.map((s, i) => {
                    const m = s.metrics_full_sample;
                    const isS = s.metrics_in_sample?.sharpe_ratio;
                    const oosS = s.metrics_out_of_sample?.sharpe_ratio;
                    const delta = isS && oosS ? ((oosS - isS) / Math.abs(isS) * 100) : null;
                    return (
                      <tr key={i} style={{ borderBottom: "1px solid #1a1a2e" }}>
                        <td style={{ padding: "10px 12px", fontWeight: 600, color: "#fff" }}>{s.metadata.strategy_name}</td>
                        <td style={{ padding: "10px 12px", color: "#6c5ce7" }}>{s.metadata.ticker}</td>
                        <td style={{ padding: "10px 12px", color: fmtColor(m.sharpe_ratio), fontWeight: 600 }}>{fmt(m.sharpe_ratio, 3)}</td>
                        <td style={{ padding: "10px 12px", color: fmtColor(m.sortino_ratio) }}>{fmt(m.sortino_ratio, 3)}</td>
                        <td style={{ padding: "10px 12px", color: fmtColor(m.total_return) }}>{fmtPct(m.total_return)}</td>
                        <td style={{ padding: "10px 12px", color: fmtColor(m.annualized_return) }}>{fmtPct(m.annualized_return)}</td>
                        <td style={{ padding: "10px 12px", color: "#e74c3c" }}>{fmtPct(m.max_drawdown)} <MiniBar value={m.max_drawdown} max={0.5} color="#e74c3c" /></td>
                        <td style={{ padding: "10px 12px" }}>{fmtPct(m.volatility)}</td>
                        <td style={{ padding: "10px 12px", color: fmtColor((m.win_rate || 0) - 50) }}>{m.win_rate?.toFixed(1)}%</td>
                        <td style={{ padding: "10px 12px", color: fmtColor((m.profit_factor || 0) - 1) }}>{fmt(m.profit_factor)}</td>
                        <td style={{ padding: "10px 12px" }}>{m.total_trades}</td>
                        <td style={{ padding: "10px 12px", color: fmtColor(oosS), fontWeight: 600 }}>{fmt(oosS, 3)}</td>
                        <td style={{ padding: "10px 12px", color: delta != null ? fmtColor(delta) : "#6a6a8a" }}>{delta != null ? `${delta > 0 ? "+" : ""}${delta.toFixed(1)}%` : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ═══ CORRELATION TAB ═══ */}
        {activeTab === "correlation" && (
          <div>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16, color: "#fff" }}>Return Correlation Matrix</h2>
            {!correlation ? (
              <p style={{ color: "#6a6a8a" }}>Load 2+ daily return CSVs to see correlations. Low correlation = good ensemble candidate.</p>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr>
                      <th style={{ padding: 10 }}></th>
                      {correlation.keys.map(k => <th key={k} style={{ padding: "10px 14px", color: "#8888aa", fontWeight: 600, fontSize: 11 }}>{k.replace(/_/g, " ")}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {correlation.keys.map(k1 => (
                      <tr key={k1}>
                        <td style={{ padding: "10px 14px", color: "#8888aa", fontWeight: 600, fontSize: 11 }}>{k1.replace(/_/g, " ")}</td>
                        {correlation.keys.map(k2 => {
                          const v = correlation.matrix[k1][k2];
                          const abs = Math.abs(v);
                          const r = v > 0 ? Math.round(40 + abs * 60) : 40;
                          const g = v < 0 ? Math.round(40 + abs * 60) : 40;
                          const bg = k1 === k2 ? "#2a2a4a" : `rgba(${v > 0 ? 231 : 46}, ${v > 0 ? 76 : 204}, ${v > 0 ? 60 : 113}, ${abs * 0.4})`;
                          return (
                            <td key={k2} style={{ padding: "10px 14px", textAlign: "center", background: bg, fontWeight: 600, borderRadius: 0,
                              color: abs > 0.5 ? "#fff" : "#aaa", fontFamily: "monospace" }}>
                              {v.toFixed(3)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p style={{ fontSize: 11, color: "#5a5a7a", marginTop: 12 }}>
                  &#9679; Green tint = negative correlation (diversifying) &middot; Red tint = positive correlation (overlapping) &middot; Ideal ensemble pairs: corr &lt; 0.3
                </p>
              </div>
            )}
          </div>
        )}

        {/* ═══ MONTE CARLO TAB ═══ */}
        {activeTab === "montecarlo" && (
          <div>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 6, color: "#fff" }}>FTMO Challenge Monte Carlo</h2>
            <p style={{ fontSize: 12, color: "#5a5a7a", marginBottom: 20 }}>
              Bootstraps 5,000 equity paths from observed daily returns. Rules: 10% target, 5% daily loss, 10% total loss, {FTMO_RULES.trading_days}-day window.
            </p>

            {Object.keys(dailyReturnsMap).length === 0 ? (
              <p style={{ color: "#6a6a8a" }}>Load daily return CSVs to run Monte Carlo simulations.</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
                {Object.entries(dailyReturnsMap).map(([key, rets]) => {
                  const mc = mcResults[key];
                  return (
                    <div key={key} style={{ background: "#111128", border: "1px solid #2a2a4a", borderRadius: 12, padding: 20 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                        <span style={{ fontSize: 16, fontWeight: 700, color: "#fff" }}>{key.replace(/_/g, " ")}</span>
                        <button onClick={() => handleRunMC(key, rets)} disabled={mcRunning === key}
                          style={{ background: mcRunning === key ? "#3a3a5a" : "#6c5ce7", color: "#fff", border: "none",
                            padding: "8px 20px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: mcRunning === key ? "wait" : "pointer" }}>
                          {mcRunning === key ? "Running..." : mc ? "Re-run" : "Run Simulation"}
                        </button>
                      </div>

                      {mc && (
                        <div>
                          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
                            <StatCard label="Pass Rate" value={`${mc.passRate.toFixed(1)}%`}
                              color={mc.passRate >= 50 ? "#2ecc71" : mc.passRate >= 25 ? "#f1c40f" : mc.passRate >= 10 ? "#e67e22" : "#e74c3c"} />
                            <StatCard label="Passed" value={mc.nPassed.toLocaleString()} sub={`of ${mc.n.toLocaleString()}`} color="#2ecc71" />
                            <StatCard label="Blown (Total)" value={mc.nBlownT.toLocaleString()} color="#e74c3c" />
                            <StatCard label="Blown (Daily)" value={mc.nBlownD.toLocaleString()} color="#e67e22" />
                            <StatCard label="Still Trading" value={mc.nStill.toLocaleString()} color="#6a6a8a" />
                          </div>

                          <div style={{ display: "flex", alignItems: "center", padding: "10px 16px", borderRadius: 8, marginBottom: 16,
                            background: mc.passRate >= 50 ? "rgba(46,204,113,0.1)" : mc.passRate >= 25 ? "rgba(241,196,15,0.1)" : "rgba(231,76,60,0.1)",
                            border: `1px solid ${mc.passRate >= 50 ? "#2ecc71" : mc.passRate >= 25 ? "#f1c40f" : "#e74c3c"}` }}>
                            <span style={{ fontSize: 20, marginRight: 10 }}>{mc.passRate >= 50 ? "🟢" : mc.passRate >= 25 ? "🟡" : mc.passRate >= 10 ? "🟠" : "🔴"}</span>
                            <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>
                              {mc.passRate >= 50 ? "FAVORABLE" : mc.passRate >= 25 ? "POSSIBLE" : mc.passRate >= 10 ? "CHALLENGING" : "UNLIKELY"}
                            </span>
                            <span style={{ fontSize: 12, color: "#8888aa", marginLeft: 12 }}>
                              {mc.passRate.toFixed(1)}% of simulations hit the 10% profit target within {FTMO_RULES.trading_days} days
                            </span>
                          </div>

                          <MonteCarloChart mc={mc} key={`${key}-${mc.n}`} />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
