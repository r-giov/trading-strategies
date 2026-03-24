import type { PortfolioSignals, PortfolioConfig, StrategySummary } from "./types";

const BASE = "/api";

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function getSignals(refresh = false): Promise<PortfolioSignals> {
  const params = refresh ? "?refresh=true" : "";
  return fetchJSON<PortfolioSignals>(`/signals/portfolio${params}`);
}

export async function getPortfolioConfig(): Promise<PortfolioConfig> {
  return fetchJSON<PortfolioConfig>(`/signals/config`);
}

export async function getStrategies(): Promise<StrategySummary[]> {
  return fetchJSON<StrategySummary[]>(`/exports/strategies`);
}
