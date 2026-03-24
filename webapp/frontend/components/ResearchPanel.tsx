"use client";

import { useState, useRef, useEffect, useCallback } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface ChatResponse {
  response: string;
  citations?: string[];
  model: string;
  usage: { input_tokens: number; output_tokens: number };
}

type Mode = "chat" | "research";

const QUICK_PROMPTS = [
  {
    label: "ASYMMETRY_CHECK",
    short: "3-leg stool",
    prompt:
      "Analyze the asymmetry of [TICKER]. Does it have a low valuation floor (based on P/S vs peers) but a high growth ceiling? Rate the Three-Legged Stool: Floor, Catalyst, Sector Heat.",
  },
  {
    label: "DEEP_DIVE",
    short: "Full report",
    prompt:
      "Generate a comprehensive research report on [TICKER]. Explain the business model, moat, top 3 competitors, and whether it has a unique advantage.",
  },
  {
    label: "RISK_REDTEAM",
    short: "Bear case",
    prompt:
      "Act as a short seller and write a 3-point bear case for [TICKER]. What are the biggest risks, the negative asymmetry scenarios, and the dilution likelihood?",
  },
  {
    label: "VALUATION",
    short: "Comp table",
    prompt:
      "Create a relative valuation table for [TICKER] comparing it to its top 3 competitors. Include: P/S ratio, EV/EBITDA, gross margin, YoY revenue growth, and Rule of 40 score.",
  },
  {
    label: "CATALYST_SCAN",
    short: "Upcoming",
    prompt:
      "Identify the top 3 upcoming catalysts for [TICKER] in the next 12 months (product launches, earnings beats, regulatory, partnerships). Rate each catalyst's probability and impact.",
  },
  {
    label: "SECTOR_HEAT",
    short: "Momentum",
    prompt:
      "Is the sector [TICKER] operates in currently 'hot'? Analyze sector momentum, institutional flows, and whether this is a cold/dead money trap.",
  },
  {
    label: "EBITDA_TURN",
    short: "Profitability",
    prompt:
      "Analyze [TICKER]'s path to profitability. When did/will they hit positive EBITDA? Are they one quarter away from the 'institutional green light'? What's the cash runway?",
  },
  {
    label: "FULL_THESIS",
    short: "Complete",
    prompt:
      "Build a complete asymmetric investment thesis for [TICKER]. Include: the macro setup, sector positioning, bottleneck they're solving, valuation floor, growth ceiling, key risks, entry strategy, and exit triggers.",
  },
];

function TradingViewChart({ ticker }: { ticker: string }) {
  if (!ticker) return null;

  // TradingView Mini Symbol Overview widget
  const src = `https://s.tradingview.com/widgetembed/?frameElementId=tv_chart&symbol=${encodeURIComponent(ticker)}&interval=D&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=050510&studies=[]&theme=dark&style=1&timezone=exchange&withdateranges=1&showpopupbutton=0&studies_overrides={}&overrides={"paneProperties.background":"#050510","paneProperties.backgroundType":"solid","scalesProperties.backgroundColor":"#050510","mainSeriesProperties.candleStyle.upColor":"#00ff88","mainSeriesProperties.candleStyle.downColor":"#ff2255","mainSeriesProperties.candleStyle.wickUpColor":"#00ff88","mainSeriesProperties.candleStyle.wickDownColor":"#ff2255"}&enabled_features=[]&disabled_features=["header_widget"]&locale=en&utm_source=localhost&utm_medium=widget_new&utm_campaign=chart`;

  return (
    <div className="rounded overflow-hidden border border-cyber-border/30" style={{ height: "200px" }}>
      <iframe
        src={`https://s.tradingview.com/widgetembed/?frameElementId=tradingview&symbol=${encodeURIComponent(ticker)}&interval=D&theme=dark&style=2&timezone=exchange&locale=en&hide_top_toolbar=1&hide_legend=0&save_image=0&backgroundColor=rgba(5,5,16,1)&gridColor=rgba(26,26,58,0.3)&width=100%25&height=200`}
        style={{ width: "100%", height: "100%", border: "none" }}
        allow="autoplay"
        title={`${ticker} chart`}
      />
    </div>
  );
}

export default function ResearchPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [ticker, setTicker] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<Mode>("chat");
  const [tokenCount, setTokenCount] = useState({ input: 0, output: 0 });
  const [showQuickPrompts, setShowQuickPrompts] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Match typed commands to quick prompts (case-insensitive)
  const COMMAND_MAP: Record<string, string> = {};
  QUICK_PROMPTS.forEach((qp) => {
    COMMAND_MAP[qp.label.toLowerCase()] = qp.prompt;
    COMMAND_MAP[qp.label.toLowerCase().replace(/_/g, " ")] = qp.prompt;
    COMMAND_MAP[qp.short.toLowerCase()] = qp.prompt;
  });

  const resolveCommand = (text: string): string => {
    const trimmed = text.trim().toLowerCase();
    const match = COMMAND_MAP[trimmed];
    if (match && ticker) {
      return match.replace(/\[TICKER\]/g, ticker);
    }
    // If they just typed a command without ticker context, still resolve
    if (match) return match.replace(/\[TICKER\]/g, ticker || "???");
    // Otherwise return the original text — it's a freeform question
    return text;
  };

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim()) return;

      // Resolve commands (case-insensitive)
      const resolved = resolveCommand(text);

      const userMsg: Message = { role: "user", content: text };
      const newMessages = [...messages, userMsg];
      setMessages(newMessages);
      setInput("");
      setLoading(true);

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ticker: ticker || "",
            message: resolved,
            context: messages.slice(-10),
            mode,
          }),
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(err.detail || err.error || "Request failed");
        }

        const data: ChatResponse = await res.json();
        setMessages([...newMessages, { role: "assistant", content: data.response }]);
        setTokenCount((prev) => ({
          input: prev.input + data.usage.input_tokens,
          output: prev.output + data.usage.output_tokens,
        }));
      } catch (err) {
        setMessages([
          ...newMessages,
          {
            role: "assistant",
            content: `ERROR: ${err instanceof Error ? err.message : "Unknown error"}`,
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [messages, ticker, mode]
  );

  const handleQuickPrompt = useCallback(
    (prompt: string) => {
      let activeTicker = ticker;
      if (!activeTicker) {
        const t = window.prompt("Enter a ticker symbol (e.g. CRDO, BE, NVDA):");
        if (!t) return;
        activeTicker = t.toUpperCase();
        setTicker(activeTicker);
      }
      const filled = prompt.replace(/\[TICKER\]/g, activeTicker);
      setShowQuickPrompts(false);
      sendMessage(filled);
    },
    [ticker, sendMessage]
  );

  const clearChat = () => {
    setMessages([]);
    setTokenCount({ input: 0, output: 0 });
  };

  const totalTokens = tokenCount.input + tokenCount.output;

  return (
    <>
      {/* Tab button visible when panel is closed */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed right-0 top-1/2 -translate-y-1/2 z-[100] bg-[#0a0a1f] border border-r-0 border-cyber-border rounded-l-md px-1.5 py-4 hover:border-cyber-accent/50 transition-all group"
          style={{
            writingMode: "vertical-rl",
            textOrientation: "mixed",
          }}
        >
          <span className="text-[10px] tracking-[3px] text-cyber-accent neon-text font-bold group-hover:text-white transition-colors">
            RESEARCH_AI
          </span>
          <span className="block w-1.5 h-1.5 rounded-full bg-cyber-accent mx-auto mt-2 animate-pulse" />
        </button>
      )}

      {/* Backdrop overlay when panel is open */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-[100] transition-opacity"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Panel */}
      <div
        className={`fixed top-0 right-0 h-screen z-[101] flex flex-col transition-transform duration-300 ease-in-out ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
        style={{ width: 450 }}
      >
        <div className="flex flex-col h-full bg-[#050510] border-l border-cyber-border">
          {/* ---- HEADER ---- */}
          <div className="flex-shrink-0 border-b border-cyber-border">
            {/* Top bar */}
            <div className="flex items-center justify-between px-3 py-2 bg-[rgba(0,212,255,0.03)]">
              <div className="flex items-center gap-2">
                <span className="text-[9px] text-cyber-accent font-bold tracking-[3px]">
                  &gt;&gt;RESEARCH_AI
                </span>
                <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              </div>
              <div className="flex items-center gap-2">
                {totalTokens > 0 && (
                  <span className="text-[9px] text-cyber-dim font-mono">
                    {totalTokens.toLocaleString()} tkn
                  </span>
                )}
                <button
                  onClick={() => setIsOpen(false)}
                  className="text-cyber-muted hover:text-white text-[11px] px-1.5 py-0.5 rounded hover:bg-white/5 transition-colors"
                  title="Minimize panel"
                >
                  [X]
                </button>
              </div>
            </div>

            {/* Ticker + Mode row */}
            <div className="flex items-center gap-2 px-3 py-2">
              <div className="flex-1 flex items-center gap-2">
                <span className="text-[9px] text-cyber-dim tracking-wider">TICKER:</span>
                <input
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  placeholder="CRDO"
                  className="w-20 bg-cyber-bg border border-cyber-border rounded px-2 py-1 text-[11px] text-cyber-accent font-bold focus:border-cyber-accent focus:outline-none text-center"
                />
              </div>

              {/* Mode selector */}
              <div className="flex rounded overflow-hidden border border-cyber-border">
                <button
                  onClick={() => setMode("chat")}
                  className={`text-[9px] px-2.5 py-1 tracking-wider transition-colors ${
                    mode === "chat"
                      ? "bg-cyber-accent/15 text-cyber-accent"
                      : "text-cyber-dim hover:text-cyber-muted"
                  }`}
                >
                  CHAT
                </button>
                <button
                  onClick={() => setMode("research")}
                  className={`text-[9px] px-2.5 py-1 tracking-wider transition-colors border-l border-cyber-border ${
                    mode === "research"
                      ? "bg-cyber-accent/15 text-cyber-accent"
                      : "text-cyber-dim hover:text-cyber-muted"
                  }`}
                >
                  REPORT
                </button>
              </div>

              {/* Clear button */}
              {messages.length > 0 && (
                <button
                  onClick={clearChat}
                  className="text-[9px] text-cyber-dim hover:text-[#ff2255] px-1.5 py-1 tracking-wider transition-colors"
                >
                  CLR
                </button>
              )}
            </div>

            {/* TradingView Chart */}
            {ticker && (
              <div className="px-3 pb-2">
                <TradingViewChart ticker={ticker} />
              </div>
            )}

            {/* Quick prompts toggle */}
            <div className="px-3 pb-2">
              <button
                onClick={() => setShowQuickPrompts(!showQuickPrompts)}
                className="text-[9px] text-cyber-muted hover:text-cyber-accent tracking-[2px] transition-colors"
              >
                {showQuickPrompts ? "[-] HIDE_COMMANDS" : "[+] QUICK_COMMANDS"}
              </button>
              {showQuickPrompts && (
                <div className="mt-2 grid grid-cols-2 gap-1">
                  {QUICK_PROMPTS.map((qp) => (
                    <button
                      key={qp.label}
                      onClick={() => handleQuickPrompt(qp.prompt)}
                      className="text-left px-2 py-1.5 rounded border border-cyber-border/50 hover:border-cyber-accent/30 hover:bg-cyber-accent/5 transition-all group"
                    >
                      <div className="text-[9px] text-cyber-accent font-bold group-hover:neon-text">
                        {qp.label}
                      </div>
                      <div className="text-[8px] text-cyber-dim">{qp.short}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* ---- MESSAGES AREA ---- */}
          <div className="flex-1 overflow-y-auto px-3 py-3">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center px-4">
                <div className="text-[9px] text-cyber-accent tracking-[4px] mb-2">
                  &gt;&gt;READY
                </div>
                <div className="text-[11px] text-cyber-muted mb-4">
                  Enter a ticker and ask a question,
                  <br />
                  or use a quick command to start.
                </div>
                <div className="terminal-panel p-3 w-full max-w-[280px]">
                  <div className="text-[9px] text-cyber-dim tracking-[2px] mb-2">
                    S&J_FRAMEWORK
                  </div>
                  <div className="space-y-1.5">
                    <div className="flex items-center gap-2">
                      <span className="w-1 h-1 rounded-full bg-cyber-accent" />
                      <span className="text-[9px] text-cyber-accent">FLOOR</span>
                      <span className="text-[8px] text-cyber-dim">Low P/S vs peers</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="w-1 h-1 rounded-full bg-[#00ff88]" />
                      <span className="text-[9px] text-[#00ff88]">CATALYST</span>
                      <span className="text-[8px] text-cyber-dim">Revenue ramp</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="w-1 h-1 rounded-full bg-[#ffaa00]" />
                      <span className="text-[9px] text-[#ffaa00]">SECTOR</span>
                      <span className="text-[8px] text-cyber-dim">Market cares NOW</span>
                    </div>
                  </div>
                </div>
                <div className="mt-4 text-[8px] text-cyber-dim">
                  Panel persists across pages. Navigate freely.
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {messages.map((msg, i) => (
                  <div
                    key={i}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[90%] rounded px-3 py-2 text-[11px] leading-relaxed ${
                        msg.role === "user"
                          ? "bg-cyber-accent/8 border border-cyber-accent/15 text-cyber-text"
                          : "bg-[#0a0a1f] border border-cyber-border text-cyber-text"
                      }`}
                    >
                      {msg.role === "assistant" && (
                        <div className="text-[9px] text-cyber-accent font-bold tracking-[2px] mb-1.5 flex items-center gap-2">
                          <span>&gt;&gt;CLAUDE</span>
                          {ticker && (
                            <span className="text-cyber-dim tracking-normal">
                              ${ticker}
                            </span>
                          )}
                        </div>
                      )}
                      {msg.role === "user" && (
                        <div className="text-[9px] text-cyber-muted tracking-[2px] mb-1">
                          &gt;&gt;YOU
                        </div>
                      )}
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                    </div>
                  </div>
                ))}
                {loading && (
                  <div className="flex justify-start">
                    <div className="bg-[#0a0a1f] border border-cyber-border rounded px-3 py-2">
                      <div className="text-[9px] text-cyber-accent font-bold tracking-[2px] mb-1">
                        &gt;&gt;CLAUDE
                      </div>
                      <div className="text-[10px] text-cyber-muted animate-pulse">
                        Analyzing{ticker ? ` $${ticker}` : ""}...
                      </div>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            )}
          </div>

          {/* ---- INPUT BAR ---- */}
          <div className="flex-shrink-0 border-t border-cyber-border px-3 py-2 bg-[#050510]">
            <div className="flex gap-2">
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage(input);
                  }
                }}
                placeholder={
                  ticker ? `Ask about $${ticker} or type a command...` : "Set ticker above, then ask anything..."
                }
                disabled={loading}
                className="flex-1 bg-cyber-bg border border-cyber-border rounded px-3 py-1.5 text-[11px] text-white placeholder-cyber-dim focus:border-cyber-accent focus:outline-none disabled:opacity-40"
              />
              <button
                onClick={() => sendMessage(input)}
                disabled={loading || !input.trim()}
                className="bg-cyber-accent/90 text-[#050510] px-4 py-1.5 rounded text-[10px] font-bold tracking-wider hover:bg-cyber-accent hover:shadow-glow transition-all disabled:opacity-20 disabled:cursor-not-allowed"
              >
                SEND
              </button>
            </div>
            <div className="mt-1.5 flex items-center justify-between text-[8px] text-cyber-dim">
              <span>
                S&J Framework // {mode === "chat" ? "Chat" : "Full Report"} mode
              </span>
              <span>Claude Sonnet // verify with SEC.gov</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
