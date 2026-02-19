"use client";

import { useState, useCallback, useEffect } from "react";

export interface IndicatorConfig {
  id: string;
  name: string;
  category: "overlay" | "oscillator";
  enabled: boolean;
  color: string;
  /** 오실레이터용: 기준선 */
  refLines?: { value: number; label: string; color: string }[];
}

const STORAGE_KEY = "indicator_toggles_v1";

const DEFAULT_INDICATORS: IndicatorConfig[] = [
  // 오버레이 (메인 차트 위)
  { id: "ema", name: "EMA", category: "overlay", enabled: false, color: "#ffb22b" },
  { id: "bb", name: "Bollinger", category: "overlay", enabled: false, color: "#8b5cf6" },
  { id: "vwap", name: "VWAP", category: "overlay", enabled: false, color: "#f97316" },
  { id: "ichimoku", name: "Ichimoku", category: "overlay", enabled: false, color: "#06b6d4" },
  // 오실레이터 (차트 아래 서브패널)
  {
    id: "rsi", name: "RSI", category: "oscillator", enabled: false, color: "#eab308",
    refLines: [
      { value: 70, label: "70", color: "rgba(239,83,80,0.4)" },
      { value: 30, label: "30", color: "rgba(38,218,210,0.4)" },
    ],
  },
  {
    id: "macd", name: "MACD", category: "oscillator", enabled: false, color: "#4680ff",
    refLines: [{ value: 0, label: "0", color: "rgba(120,130,140,0.3)" }],
  },
  {
    id: "stoch", name: "Stochastic", category: "oscillator", enabled: false, color: "#ec4899",
    refLines: [
      { value: 80, label: "80", color: "rgba(239,83,80,0.4)" },
      { value: 20, label: "20", color: "rgba(38,218,210,0.4)" },
    ],
  },
  { id: "adx", name: "ADX", category: "oscillator", enabled: false, color: "#14b8a6",
    refLines: [{ value: 20, label: "20", color: "rgba(120,130,140,0.3)" }],
  },
  {
    id: "williams_r", name: "W%R", category: "oscillator", enabled: false, color: "#f43f5e",
    refLines: [
      { value: -20, label: "-20", color: "rgba(239,83,80,0.4)" },
      { value: -80, label: "-80", color: "rgba(38,218,210,0.4)" },
    ],
  },
  {
    id: "cci", name: "CCI", category: "oscillator", enabled: false, color: "#a855f7",
    refLines: [
      { value: 100, label: "100", color: "rgba(239,83,80,0.4)" },
      { value: -100, label: "-100", color: "rgba(38,218,210,0.4)" },
    ],
  },
  {
    id: "mfi", name: "MFI", category: "oscillator", enabled: false, color: "#22c55e",
    refLines: [
      { value: 80, label: "80", color: "rgba(239,83,80,0.4)" },
      { value: 20, label: "20", color: "rgba(38,218,210,0.4)" },
    ],
  },
  {
    id: "cmf", name: "CMF", category: "oscillator", enabled: false, color: "#0ea5e9",
    refLines: [{ value: 0, label: "0", color: "rgba(120,130,140,0.3)" }],
  },
];

export function useIndicatorToggles() {
  const [indicators, setIndicators] = useState<IndicatorConfig[]>(() => {
    if (typeof window === "undefined") return DEFAULT_INDICATORS;
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed: Record<string, boolean> = JSON.parse(saved);
        return DEFAULT_INDICATORS.map((ind) => ({
          ...ind,
          enabled: parsed[ind.id] ?? ind.enabled,
        }));
      }
    } catch {}
    return DEFAULT_INDICATORS;
  });

  // localStorage에 저장
  useEffect(() => {
    const map: Record<string, boolean> = {};
    indicators.forEach((ind) => { map[ind.id] = ind.enabled; });
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
    } catch {}
  }, [indicators]);

  const toggle = useCallback((id: string) => {
    setIndicators((prev) =>
      prev.map((ind) => (ind.id === id ? { ...ind, enabled: !ind.enabled } : ind))
    );
  }, []);

  const enabledIds = indicators.filter((i) => i.enabled).map((i) => i.id);
  const enabledOverlays = indicators.filter((i) => i.enabled && i.category === "overlay");
  const enabledOscillators = indicators.filter((i) => i.enabled && i.category === "oscillator");

  return { indicators, toggle, enabledIds, enabledOverlays, enabledOscillators };
}
