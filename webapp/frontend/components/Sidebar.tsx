"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";

const NAV_ITEMS = [
  { href: "/dashboard", label: "DASHBOARD", icon: "01" },
  { href: "/strategies", label: "STRATEGIES", icon: "02" },
  { href: "/backtest", label: "BACKTEST", icon: "03" },
  { href: "/ftmo", label: "FTMO", icon: "04" },
  { href: "/research", label: "RESEARCH_AI", icon: "05" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [time, setTime] = useState("--:--:--");

  useEffect(() => {
    const update = () => setTime(new Date().toISOString().slice(11, 19));
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <aside className="w-56 h-screen bg-[#050510] border-r border-cyber-border flex flex-col fixed left-0 top-0">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-cyber-border">
        <div className="text-[10px] text-cyber-muted mb-1 tracking-[4px]">&gt;&gt;SYSTEM</div>
        <h1 className="text-base font-bold tracking-tight text-white neon-text">
          QS_FINANCE
        </h1>
        <div className="text-[9px] text-cyber-muted mt-1 tracking-[3px]">
          TRADING_PLATFORM v2.0
        </div>
        <div className="h-px bg-gradient-to-r from-cyber-accent/50 to-transparent mt-3" />
      </div>

      {/* Connection indicator */}
      <div className="px-4 py-2 border-b border-cyber-border/50">
        <div className="flex items-center gap-2 text-[9px] tracking-wider">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
          <span className="text-green-400">CONNECTED</span>
        </div>
        <div className="text-[9px] text-cyber-dim mt-0.5">MT5 // FTMO-DEMO</div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-2">
        <div className="text-[9px] text-cyber-dim px-2 mb-2 tracking-[3px]">&gt;&gt;MODULES</div>
        {NAV_ITEMS.map((item) => {
          const active = pathname?.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-2 px-3 py-2 rounded mb-0.5 text-[11px] font-medium transition-all ${
                active
                  ? "bg-cyber-accent/10 text-cyber-accent border-l-2 border-cyber-accent neon-text"
                  : "text-cyber-muted hover:text-cyber-text hover:bg-white/[0.02] border-l-2 border-transparent"
              }`}
            >
              <span className={`text-[9px] ${active ? "text-cyber-accent" : "text-cyber-dim"}`}>
                [{item.icon}]
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* System info */}
      <div className="px-4 py-3 border-t border-cyber-border">
        <div className="text-[9px] text-cyber-dim tracking-[2px] mb-1">&gt;&gt;ACCOUNT</div>
        <div className="text-[10px] text-cyber-muted">FTMO $100K CHALLENGE</div>
        <div className="text-[10px] text-cyber-muted">CRYPTO PORTFOLIO v1.0</div>
        <div className="h-px bg-gradient-to-r from-cyber-border to-transparent mt-2 mb-2" />
        <div className="text-[8px] text-cyber-dim tracking-wider">
          SYS.TIME {time} UTC
        </div>
      </div>
    </aside>
  );
}
