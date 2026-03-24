interface RiskGaugeProps {
  label: string;
  current: number;
  max: number;
  color: string;
  format?: "currency" | "percent";
}

export default function RiskGauge({ label, current, max, color, format = "currency" }: RiskGaugeProps) {
  const pct = Math.min(Math.abs(current) / max * 100, 100);
  const displayVal = format === "currency"
    ? `$${Math.abs(current).toLocaleString()}`
    : `${(current * 100).toFixed(1)}%`;
  const displayMax = format === "currency"
    ? `$${max.toLocaleString()}`
    : `${(max * 100).toFixed(1)}%`;

  return (
    <div className="flex-1 min-w-[200px]">
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-[11px] text-cyber-muted uppercase tracking-wider">{label}</span>
        <span className="text-[12px] font-mono text-cyber-text">
          {displayVal} / {displayMax}
        </span>
      </div>
      <div className="w-full h-2 bg-cyber-bg rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}
