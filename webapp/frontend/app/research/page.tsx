"use client";

export default function ResearchPage() {
  return (
    <div className="p-5 max-w-5xl mx-auto">
      <div className="text-[9px] text-cyber-accent tracking-[4px] mb-1">&gt;&gt;RESEARCH_AI</div>
      <h1 className="text-xl font-bold text-white neon-text mb-2">RESEARCH_TERMINAL</h1>
      <p className="text-[11px] text-cyber-dim mb-6">
        Use the Research AI panel (right side) to analyze any stock.
        The panel stays open as you navigate the platform.
      </p>

      {/* S&J Framework overview */}
      <div className="terminal-panel p-5 mb-5">
        <div className="terminal-header mb-3">S&J_ASYMMETRIC_FRAMEWORK</div>
        <p className="text-[11px] text-cyber-muted mb-4 px-3">
          Find mispriced growth stocks with high floors and higher ceilings.
          The framework evaluates three independent legs — all three must hold
          for an asymmetric opportunity.
        </p>
        <div className="grid grid-cols-3 gap-4 px-3">
          <div className="terminal-panel p-3">
            <div className="text-[10px] text-cyber-accent font-bold mb-1">LEG 1: FLOOR</div>
            <div className="text-[10px] text-cyber-dim">
              Low P/S vs peers = compressed valuation. The stock has a
              quantifiable downside floor.
            </div>
          </div>
          <div className="terminal-panel p-3">
            <div className="text-[10px] text-[#00ff88] font-bold mb-1">LEG 2: CATALYST</div>
            <div className="text-[10px] text-cyber-dim">
              Rapid revenue ramp, EBITDA turn, or inflection event.
              The machine is working.
            </div>
          </div>
          <div className="terminal-panel p-3">
            <div className="text-[10px] text-[#ffaa00] font-bold mb-1">LEG 3: SECTOR</div>
            <div className="text-[10px] text-cyber-dim">
              Market cares about this industry NOW. Capital is flowing
              in, not dead money.
            </div>
          </div>
        </div>
      </div>

      {/* Available commands */}
      <div className="terminal-panel p-5 mb-5">
        <div className="terminal-header mb-3">AVAILABLE_COMMANDS</div>
        <div className="space-y-2 text-[11px] px-3">
          <div>
            <span className="text-cyber-accent">DEEP_DIVE</span>{" "}
            <span className="text-cyber-dim">
              — Full 10-section research report: business model, moat, competitors, advantage
            </span>
          </div>
          <div>
            <span className="text-cyber-accent">ASYMMETRY_CHECK</span>{" "}
            <span className="text-cyber-dim">
              — Three-legged stool analysis: floor, catalyst, sector heat ratings
            </span>
          </div>
          <div>
            <span className="text-cyber-accent">VALUATION</span>{" "}
            <span className="text-cyber-dim">
              — P/S, EV/EBITDA, gross margin, growth vs top 3 peers
            </span>
          </div>
          <div>
            <span className="text-cyber-accent">RISK_REDTEAM</span>{" "}
            <span className="text-cyber-dim">
              — Bear case, tail risks, dilution analysis from short-seller perspective
            </span>
          </div>
          <div>
            <span className="text-cyber-accent">CATALYST_SCAN</span>{" "}
            <span className="text-cyber-dim">
              — Top 3 upcoming catalysts with probability and impact ratings
            </span>
          </div>
          <div>
            <span className="text-cyber-accent">SECTOR_HEAT</span>{" "}
            <span className="text-cyber-dim">
              — Sector momentum, institutional flows, dead money check
            </span>
          </div>
          <div>
            <span className="text-cyber-accent">EBITDA_TURN</span>{" "}
            <span className="text-cyber-dim">
              — Path to profitability, cash runway, institutional green light proximity
            </span>
          </div>
          <div>
            <span className="text-cyber-accent">FULL_THESIS</span>{" "}
            <span className="text-cyber-dim">
              — Complete asymmetric thesis: macro, positioning, valuation, risks, triggers
            </span>
          </div>
        </div>
      </div>

      {/* Usage guide */}
      <div className="terminal-panel p-5">
        <div className="terminal-header mb-3">USAGE_GUIDE</div>
        <div className="space-y-3 text-[11px] px-3">
          <div className="flex items-start gap-3">
            <span className="text-cyber-accent font-bold text-[10px] mt-0.5">01</span>
            <div>
              <div className="text-cyber-text font-medium">Open the panel</div>
              <div className="text-cyber-dim text-[10px]">
                Click the &quot;RESEARCH_AI&quot; tab on the right edge of any page
              </div>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <span className="text-cyber-accent font-bold text-[10px] mt-0.5">02</span>
            <div>
              <div className="text-cyber-text font-medium">Enter a ticker</div>
              <div className="text-cyber-dim text-[10px]">
                Type any stock symbol (CRDO, BE, NVDA) in the ticker field
              </div>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <span className="text-cyber-accent font-bold text-[10px] mt-0.5">03</span>
            <div>
              <div className="text-cyber-text font-medium">Ask or use a quick command</div>
              <div className="text-cyber-dim text-[10px]">
                Type a question or expand Quick Commands for pre-built prompts
              </div>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <span className="text-cyber-accent font-bold text-[10px] mt-0.5">04</span>
            <div>
              <div className="text-cyber-text font-medium">Navigate freely</div>
              <div className="text-cyber-dim text-[10px]">
                The panel stays open across Dashboard, Strategies, Backtest, and FTMO pages.
                Your chat history persists until you clear or refresh.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
