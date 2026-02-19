"use client";

import { useEffect, useRef, useCallback } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  IPriceLine,
  CandlestickData,
  HistogramData,
  LineData,
  LogicalRange,
} from "lightweight-charts";
import { Candle, Prediction, PredictionPoint, IndicatorSeriesResponse, IndicatorSeriesPoint } from "@/lib/api";
import { IndicatorConfig } from "@/hooks/useIndicatorToggles";

interface CandleChartProps {
  candles: Candle[];
  symbol: string;
  prediction?: Prediction | null;
  indicatorData?: IndicatorSeriesResponse | null;
  enabledIndicators?: IndicatorConfig[];
}

// lightweight-charts는 canvas이므로 hex 하드코딩 필수 (CSS vars 사용 불가)
// 디자인 토큰: body=#070713, text=#abafb3, border=rgba(120,130,140,0.13)
// long=#26dad2, short=#ef5350, primary=#4680ff, warning=#ffb22b

const CHART_BG = "#070713";
const CHART_TEXT = "#abafb3";
const GRID_COLOR = "rgba(120, 130, 140, 0.13)";

// 오버레이 시리즈 색상 매핑 (지표별 서브시리즈)
const OVERLAY_SERIES_COLORS: Record<string, Record<string, { color: string; width: number; style?: number }>> = {
  ema: {
    ema_short: { color: "#ffb22b", width: 1 },
    ema_long: { color: "#ff6b35", width: 1 },
  },
  bb: {
    bb_upper: { color: "#8b5cf6", width: 1, style: 2 },
    bb_middle: { color: "#8b5cf6", width: 1 },
    bb_lower: { color: "#8b5cf6", width: 1, style: 2 },
  },
  vwap: {
    vwap: { color: "#f97316", width: 2 },
  },
  ichimoku: {
    tenkan: { color: "#06b6d4", width: 1 },
    kijun: { color: "#e11d48", width: 1 },
    isa: { color: "rgba(38,218,210,0.3)", width: 1 },
    isb: { color: "rgba(239,83,80,0.3)", width: 1 },
  },
};

function toLineData(points: IndicatorSeriesPoint[]): LineData[] {
  const tz = -new Date().getTimezoneOffset() * 60;
  return points.map((p) => ({ time: (p.time + tz) as any, value: p.value }));
}

export default function CandleChart({
  candles,
  symbol,
  prediction,
  indicatorData,
  enabledIndicators,
}: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const subPanelRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const predLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const predUpperRef = useRef<ISeriesApi<"Line"> | null>(null);
  const predLowerRef = useRef<ISeriesApi<"Line"> | null>(null);
  const actualLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);

  // 오버레이 시리즈 맵: "ema.ema_short" → ISeriesApi
  const overlaySeriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  // 서브차트 맵: "rsi" → { chart, series[] }
  const subChartsRef = useRef<Map<string, { chart: IChartApi; series: ISeriesApi<"Line" | "Histogram">[] }>>(new Map());

  const syncingRef = useRef(false);

  // ─── 메인 차트 초기화 ──────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;
    const getHeight = () => (window.innerWidth < 640 ? 360 : 500);

    const chart = createChart(containerRef.current, {
      layout: { background: { color: CHART_BG }, textColor: CHART_TEXT },
      grid: { vertLines: { color: GRID_COLOR }, horzLines: { color: GRID_COLOR } },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: GRID_COLOR },
      timeScale: { borderColor: GRID_COLOR, timeVisible: true },
      width: containerRef.current.clientWidth,
      height: getHeight(),
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#26dad2", downColor: "#ef5350",
      borderDownColor: "#ef5350", borderUpColor: "#26dad2",
      wickDownColor: "#ef5350", wickUpColor: "#26dad2",
    });

    const volumeSeries = chart.addHistogramSeries({
      color: "#26a69a", priceFormat: { type: "volume" }, priceScaleId: "",
    });
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    const predLine = chart.addLineSeries({ color: "#4680ff", lineWidth: 2, lineStyle: 2, crosshairMarkerVisible: false, priceLineVisible: false, lastValueVisible: false });
    const predUpper = chart.addLineSeries({ color: "rgba(70,128,255,0.25)", lineWidth: 1, lineStyle: 1, crosshairMarkerVisible: false, priceLineVisible: false, lastValueVisible: false });
    const predLower = chart.addLineSeries({ color: "rgba(70,128,255,0.25)", lineWidth: 1, lineStyle: 1, crosshairMarkerVisible: false, priceLineVisible: false, lastValueVisible: false });
    const actualLine = chart.addLineSeries({ color: "#ffb22b", lineWidth: 2, lineStyle: 0, crosshairMarkerVisible: false, priceLineVisible: false, lastValueVisible: false });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    predLineRef.current = predLine;
    predUpperRef.current = predUpper;
    predLowerRef.current = predLower;
    actualLineRef.current = actualLine;

    let resizeTimer: ReturnType<typeof setTimeout>;
    const ro = new ResizeObserver((entries) => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        for (const entry of entries) {
          chart.applyOptions({ width: entry.contentRect.width, height: getHeight() });
          // 서브차트도 리사이즈
          subChartsRef.current.forEach(({ chart: sc }) => {
            sc.applyOptions({ width: entry.contentRect.width });
          });
        }
      }, 100);
    });
    ro.observe(containerRef.current);

    return () => {
      clearTimeout(resizeTimer);
      ro.disconnect();
      // 서브차트 정리
      subChartsRef.current.forEach(({ chart: sc }) => sc.remove());
      subChartsRef.current.clear();
      overlaySeriesRef.current.clear();
      chart.remove();
    };
  }, []);

  // ─── 캔들 데이터 업데이트 ──────────────────────────────
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || !candles.length) return;
    const tz = -new Date().getTimezoneOffset() * 60;

    const candleData: CandlestickData[] = candles.map((c) => ({
      time: (c.time + tz) as any, open: c.open, high: c.high, low: c.low, close: c.close,
    }));
    const volumeData: HistogramData[] = candles.map((c) => ({
      time: (c.time + tz) as any, value: c.volume,
      color: c.close >= c.open ? "rgba(38,218,210,0.3)" : "rgba(239,83,80,0.3)",
    }));

    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current.setData(volumeData);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  // ─── 예측 데이터 ───────────────────────────────────────
  useEffect(() => {
    if (!predLineRef.current || !predUpperRef.current || !predLowerRef.current || !actualLineRef.current) return;
    if (!prediction || !prediction.predicted_path?.length) {
      predLineRef.current.setData([]); predUpperRef.current.setData([]);
      predLowerRef.current.setData([]); actualLineRef.current.setData([]);
      return;
    }
    const tz = -new Date().getTimezoneOffset() * 60;
    const mapPath = (path: PredictionPoint[]): LineData[] => path.map((p) => ({ time: (p.time + tz) as any, value: p.price }));
    predLineRef.current.setData(mapPath(prediction.predicted_path));
    predUpperRef.current.setData(mapPath(prediction.upper_bound_path));
    predLowerRef.current.setData(mapPath(prediction.lower_bound_path));
    actualLineRef.current.setData(prediction.actual_path?.length ? mapPath(prediction.actual_path) : []);
  }, [prediction]);

  // ─── TP/SL 수평선 ─────────────────────────────────────
  useEffect(() => {
    if (!candleSeriesRef.current) return;
    for (const line of priceLinesRef.current) {
      try { candleSeriesRef.current.removePriceLine(line); } catch {}
    }
    priceLinesRef.current = [];
    if (!prediction || prediction.status !== "ACTIVE") return;
    const lines = [
      { price: prediction.entry_price, title: "Entry", color: "#4680ff" },
      { price: prediction.stop_loss, title: "SL", color: "#ef5350" },
      { price: prediction.take_profit_1, title: "TP1", color: "#26dad2" },
      { price: prediction.take_profit_2, title: "TP2", color: "#26dad2" },
      { price: prediction.take_profit_3, title: "TP3", color: "#26dad2" },
    ];
    for (const { price, title, color } of lines) {
      if (!price) continue;
      priceLinesRef.current.push(
        candleSeriesRef.current.createPriceLine({ price, color, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title })
      );
    }
  }, [prediction]);

  // ─── 오버레이 지표 시리즈 관리 ─────────────────────────
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const enabledOverlayIds = new Set(
      (enabledIndicators || []).filter((i) => i.category === "overlay").map((i) => i.id)
    );

    // 비활성화된 오버레이 제거
    overlaySeriesRef.current.forEach((series, key) => {
      const [indId] = key.split(".");
      if (!enabledOverlayIds.has(indId)) {
        try { chart.removeSeries(series); } catch {}
        overlaySeriesRef.current.delete(key);
      }
    });

    // 활성화된 오버레이 추가/업데이트
    enabledOverlayIds.forEach((indId) => {
      const seriesConfig = OVERLAY_SERIES_COLORS[indId];
      const indData = indicatorData?.indicators?.[indId];
      if (!seriesConfig || !indData) return;

      Object.entries(seriesConfig).forEach(([seriesName, config]) => {
        const key = `${indId}.${seriesName}`;
        const points = indData[seriesName];
        if (!points?.length) return;

        let series = overlaySeriesRef.current.get(key);
        if (!series) {
          series = chart.addLineSeries({
            color: config.color,
            lineWidth: config.width as any,
            lineStyle: config.style || 0,
            crosshairMarkerVisible: false,
            priceLineVisible: false,
            lastValueVisible: false,
          });
          overlaySeriesRef.current.set(key, series);
        }
        series.setData(toLineData(points));
      });
    });
  }, [indicatorData, enabledIndicators]);

  // ─── 오실레이터 서브패널 관리 ──────────────────────────
  useEffect(() => {
    const mainChart = chartRef.current;
    const container = subPanelRef.current;
    if (!mainChart || !container) return;

    const enabledOsc = (enabledIndicators || []).filter((i) => i.category === "oscillator" && i.enabled);
    const enabledIds = new Set(enabledOsc.map((i) => i.id));

    // 비활성화된 서브차트 제거
    subChartsRef.current.forEach(({ chart: sc }, key) => {
      if (!enabledIds.has(key)) {
        sc.remove();
        subChartsRef.current.delete(key);
        const el = container.querySelector(`[data-ind="${key}"]`);
        if (el) el.remove();
      }
    });

    // 활성화된 서브차트 생성/업데이트
    enabledOsc.forEach((ind) => {
      const indData = indicatorData?.indicators?.[ind.id];
      if (!indData) return;

      let entry = subChartsRef.current.get(ind.id);

      if (!entry) {
        // 컨테이너 div 생성
        let wrapper = container.querySelector(`[data-ind="${ind.id}"]`) as HTMLDivElement;
        if (!wrapper) {
          wrapper = document.createElement("div");
          wrapper.setAttribute("data-ind", ind.id);
          wrapper.style.position = "relative";
          container.appendChild(wrapper);

          // 라벨 오버레이
          const label = document.createElement("div");
          label.style.cssText = `position:absolute;top:4px;left:8px;z-index:2;font-size:10px;color:${ind.color};font-weight:600;pointer-events:none;`;
          label.textContent = ind.name;
          wrapper.appendChild(label);
        }

        const chartDiv = document.createElement("div");
        wrapper.appendChild(chartDiv);

        const width = containerRef.current?.clientWidth || 800;
        const subChart = createChart(chartDiv, {
          layout: { background: { color: CHART_BG }, textColor: CHART_TEXT },
          grid: { vertLines: { color: GRID_COLOR }, horzLines: { color: GRID_COLOR } },
          rightPriceScale: { borderColor: GRID_COLOR },
          timeScale: { visible: false },
          crosshair: { mode: 0 },
          width,
          height: 80,
        });

        // 기준선 추가
        if (ind.refLines) {
          const refSeries = subChart.addLineSeries({
            color: "transparent",
            lineWidth: 1,
            lineStyle: 3,
            crosshairMarkerVisible: false,
            priceLineVisible: false,
            lastValueVisible: false,
            visible: false,
          });
          // 최소한의 데이터로 기준선만 그리기
          const firstKey = Object.keys(indData)[0];
          const pts = indData[firstKey];
          if (pts?.length) {
            refSeries.setData(toLineData(pts).slice(0, 1));
            ind.refLines.forEach((rl) => {
              refSeries.createPriceLine({
                price: rl.value,
                color: rl.color,
                lineWidth: 1,
                lineStyle: 2,
                axisLabelVisible: false,
                title: "",
              });
            });
          }
        }

        entry = { chart: subChart, series: [] };
        subChartsRef.current.set(ind.id, entry);

        // 타임스케일 동기화
        mainChart.timeScale().subscribeVisibleLogicalRangeChange((range: LogicalRange | null) => {
          if (syncingRef.current || !range) return;
          syncingRef.current = true;
          try { subChart.timeScale().setVisibleLogicalRange(range); } catch {}
          syncingRef.current = false;
        });
        subChart.timeScale().subscribeVisibleLogicalRangeChange((range: LogicalRange | null) => {
          if (syncingRef.current || !range) return;
          syncingRef.current = true;
          try { mainChart.timeScale().setVisibleLogicalRange(range); } catch {}
          syncingRef.current = false;
        });
      }

      const subChart = entry.chart;

      // 기존 시리즈 제거
      entry.series.forEach((s) => {
        try { subChart.removeSeries(s); } catch {}
      });
      entry.series = [];

      // MACD는 히스토그램 + 2라인 특수 처리
      if (ind.id === "macd") {
        const hist = indData["histogram"];
        if (hist?.length) {
          const histSeries = subChart.addHistogramSeries({
            color: "#4680ff", priceFormat: { type: "price" }, priceScaleId: "right",
          });
          const histData: HistogramData[] = hist.map((p) => {
            const tz = -new Date().getTimezoneOffset() * 60;
            return {
              time: (p.time + tz) as any,
              value: p.value,
              color: p.value >= 0 ? "rgba(38,218,210,0.4)" : "rgba(239,83,80,0.4)",
            };
          });
          histSeries.setData(histData);
          entry.series.push(histSeries as any);
        }
        ["macd_line", "signal_line"].forEach((name, i) => {
          const pts = indData[name];
          if (!pts?.length) return;
          const s = subChart.addLineSeries({
            color: i === 0 ? "#4680ff" : "#ff6b35",
            lineWidth: 1,
            crosshairMarkerVisible: false,
            priceLineVisible: false,
            lastValueVisible: false,
          });
          s.setData(toLineData(pts));
          entry!.series.push(s);
        });
      } else {
        // 일반 오실레이터: 모든 시리즈를 라인으로
        const colors = [ind.color, "#ff6b35", "#22c55e"];
        Object.keys(indData).forEach((seriesName, i) => {
          const pts = indData[seriesName];
          if (!pts?.length) return;
          const s = subChart.addLineSeries({
            color: colors[i % colors.length],
            lineWidth: 1,
            crosshairMarkerVisible: false,
            priceLineVisible: false,
            lastValueVisible: false,
          });
          s.setData(toLineData(pts));
          entry!.series.push(s);
        });
      }

      subChart.timeScale().fitContent();
    });
  }, [indicatorData, enabledIndicators]);

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="px-4 py-2 bg-card border-b border-border flex items-center justify-between">
        <span className="font-medium">{symbol}</span>
        <div className="flex items-center gap-2 text-xs flex-wrap">
          {/* 활성 오버레이 범례 */}
          {(enabledIndicators || [])
            .filter((i) => i.enabled && i.category === "overlay")
            .map((ind) => (
              <span key={ind.id} className="flex items-center gap-1">
                <span className="w-3 h-0.5 inline-block rounded" style={{ backgroundColor: ind.color }} />
                <span style={{ color: ind.color }}>{ind.name}</span>
              </span>
            ))}
          {prediction && (
            <>
              <span className="w-3 h-0.5 inline-block" style={{ borderTop: "2px dashed #4680ff" }} />
              <span className="text-primary">예측</span>
              {prediction.actual_path && (
                <>
                  <span className="w-3 h-0.5 inline-block" style={{ backgroundColor: "#ffb22b" }} />
                  <span className="text-warning">실제</span>
                </>
              )}
            </>
          )}
        </div>
      </div>
      <div ref={containerRef} />
      <div ref={subPanelRef} />
    </div>
  );
}
