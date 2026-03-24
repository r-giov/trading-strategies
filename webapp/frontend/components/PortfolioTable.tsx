import type { AggregatedSignal } from "@/lib/types";

const ACTION_COLORS: Record<string, string> = {
  BUY: "#2ecc71",
  SELL: "#e74c3c",
  HOLD: "#6a6a8a",
};

interface Props {
  aggregated: Record<string, AggregatedSignal>;
}

export default function PortfolioTable({ aggregated }: Props) {
  const entries = Object.entries(aggregated);

  if (entries.length === 0) return null;

  return (
    <div className="bg-cyber-surface border border-cyber-border rounded-lg overflow-hidden">
      <div className="px-5 py-3 border-b border-cyber-border">
        <h3 className="text-sm font-bold text-white">Aggregated Positions</h3>
        <p className="text-[11px] text-cyber-muted mt-0.5">Net signal per symbol (Donchian + MACD combined)</p>
      </div>
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-cyber-border/50">
            <th className="text-left px-5 py-2.5 text-[11px] text-cyber-muted uppercase tracking-wider font-semibold">Symbol</th>
            <th className="text-left px-5 py-2.5 text-[11px] text-cyber-muted uppercase tracking-wider font-semibold">Action</th>
            <th className="text-left px-5 py-2.5 text-[11px] text-cyber-muted uppercase tracking-wider font-semibold">Weight</th>
            <th className="text-left px-5 py-2.5 text-[11px] text-cyber-muted uppercase tracking-wider font-semibold">Last Close</th>
            <th className="text-left px-5 py-2.5 text-[11px] text-cyber-muted uppercase tracking-wider font-semibold">Breakdown</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([symbol, agg]) => (
            <tr key={symbol} className="border-b border-cyber-border/30 hover:bg-white/[0.02]">
              <td className="px-5 py-3 font-mono font-semibold text-cyber-accent">{symbol}</td>
              <td className="px-5 py-3">
                <span
                  className="font-bold font-mono text-xs px-2.5 py-0.5 rounded-full"
                  style={{
                    color: ACTION_COLORS[agg.action],
                    backgroundColor: `${ACTION_COLORS[agg.action]}20`,
                  }}
                >
                  {agg.action}
                </span>
              </td>
              <td className="px-5 py-3 font-mono text-white">
                {agg.weight > 0 ? `${(agg.weight * 100).toFixed(1)}%` : "—"}
              </td>
              <td className="px-5 py-3 font-mono text-white">
                {agg.last_close ? `$${agg.last_close.toLocaleString()}` : "—"}
              </td>
              <td className="px-5 py-3 text-cyber-muted text-[12px]">{agg.summary}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
