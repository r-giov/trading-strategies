interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}

export default function StatCard({ label, value, sub, color = "#c0c0d8" }: StatCardProps) {
  return (
    <div className="terminal-panel px-4 py-3 min-w-[130px]">
      <div className="text-[9px] text-cyber-muted uppercase tracking-[2px] mb-1">
        {label}
      </div>
      <div className="text-lg font-bold data-grid" style={{ color }}>
        {value}
      </div>
      {sub && (
        <div className="text-[9px] text-cyber-dim mt-0.5">{sub}</div>
      )}
    </div>
  );
}
