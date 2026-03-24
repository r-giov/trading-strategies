export interface ComponentSignal {
  component_id: string;
  symbol: string;
  strategy: string;
  weight: number;
  action: "BUY" | "SELL" | "HOLD";
  crossover: boolean;
  reason: string;
  indicators: Record<string, number>;
  last_close?: number;
  bar_time?: string;
  timestamp?: string;
}

export interface AggregatedSignal {
  action: "BUY" | "SELL" | "HOLD";
  weight: number;
  last_close: number | null;
  summary: string;
  components: ComponentSignal[];
}

export interface PortfolioSignals {
  components: ComponentSignal[];
  aggregated: Record<string, AggregatedSignal>;
  timestamp: string | null;
}

export interface PortfolioComponent {
  id: string;
  symbol: string;
  yf_ticker: string;
  strategy: string;
  weight: number;
  oos_sharpe: number | null;
  ftmo_pass_rate: number | null;
}

export interface PortfolioConfig {
  account_size: number;
  profit_target: number;
  max_daily_loss: number;
  max_total_loss: number;
  symbols: string[];
  components: PortfolioComponent[];
}

export interface StrategySummary {
  strategy: string;
  ticker: string;
  summary: {
    metadata: {
      strategy_name: string;
      ticker: string;
      start_date: string;
      end_date: string;
      train_end: string;
    };
    best_params: Record<string, number>;
    metrics_full_sample: {
      sharpe_ratio: number;
      total_return: number;
      max_drawdown: number;
      win_rate: number;
      profit_factor: number;
      total_trades: number;
      trades_per_year: number;
      calmar_ratio: number;
      sortino_ratio: number;
      annualized_return: number;
      volatility: number;
    };
    metrics_in_sample?: {
      sharpe_ratio: number;
    };
    metrics_out_of_sample?: {
      sharpe_ratio: number;
    };
  };
}
