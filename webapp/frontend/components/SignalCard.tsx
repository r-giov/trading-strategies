import type { ComponentSignal } from "@/lib/types";

const ACTION_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  BUY: { bg: "rgba(46, 204, 113, 0.1)", text: "#2ecc71", border: "border-green-500/30" },
  SELL: { bg: "rgba(231, 76, 60, 0.1)", text: "#e74c3c", border: "border-red-500/30" },
  HOLD: { bg: "rgba(106, 106, 138, 0.1)", text: "#6a6a8a", border: "border-cyber-border" },
};

export default function SignalCard({ signal }: { signal: ComponentSignal }) {
  const style = ACTION_STYLES[signal.action] || ACTION_STYLES.HOLD;

  return (
    <div
      className={`bg-cyber-surface border ${style.border} rounded-lg p-4 transition-all hover:shadow-glow`}
      style={{ backgroundColor: style.bg }}
    >
      <div className="flex justify-between items-start mb-3">
        <div>
          <span className="text-sm font-bold text-white">{signal.component_id}</span>
          <div className="text-[11px] text-cyber-muted mt-0.5">
            {signal.strategy.replace(/_/g, " ")}
          </div>
        </div>
        <span
          className="text-xs font-bold px-3 py-1 rounded-full font-mono"
          style={{ color: style.text, backgroundColor: `${style.text}20` }}
        >
          {signal.action}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-[12px]">
        <div>
          <span className="text-cyber-muted">Symbol </span>
          <span className="text-cyber-accent font-mono font-semibold">{signal.symbol}</span>
        </div>
        <div>
          <span className="text-cyber-muted">Weight </span>
          <span className="text-white font-mono">{(signal.weight * 100).toFixed(1)}%</span>
        </div>
        {signal.last_close && (
          <div>
            <span className="text-cyber-muted">Last </span>
            <span className="text-white font-mono">${signal.last_close.toLocaleString()}</span>
          </div>
        )}
        <div className="col-span-2">
          <span className="text-cyber-muted">Reason </span>
          <span className="text-cyber-dim">{signal.reason}</span>
        </div>
      </div>

      {Object.keys(signal.indicators).length > 0 && (
        <div className="mt-2 pt-2 border-t border-cyber-border/50 flex gap-3 text-[11px]">
          {Object.entries(signal.indicators).map(([key, val]) => (
            <div key={key}>
              <span className="text-cyber-muted">{key}: </span>
              <span className="text-cyber-text font-mono">{typeof val === "number" ? val.toFixed(4) : val}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
