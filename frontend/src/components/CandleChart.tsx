"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  IPriceLine,
  CandlestickData,
  HistogramData,
  LineData,
} from "lightweight-charts";
import { Candle, Prediction, PredictionPoint } from "@/lib/api";

interface CandleChartProps {
  candles: Candle[];
  symbol: string;
  prediction?: Prediction | null;
}

export default function CandleChart({ candles, symbol, prediction }: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const predLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const predUpperRef = useRef<ISeriesApi<"Line"> | null>(null);
  const predLowerRef = useRef<ISeriesApi<"Line"> | null>(null);
  const actualLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "#070713" },
        textColor: "#abafb3",
      },
      grid: {
        vertLines: { color: "rgba(120, 130, 140, 0.13)" },
        horzLines: { color: "rgba(120, 130, 140, 0.13)" },
      },
      crosshair: {
        mode: 0,
      },
      rightPriceScale: {
        borderColor: "rgba(120, 130, 140, 0.13)",
      },
      timeScale: {
        borderColor: "rgba(120, 130, 140, 0.13)",
        timeVisible: true,
      },
      width: containerRef.current.clientWidth,
      height: 500,
    });

    // 캔들스틱 시리즈
    const candleSeries = chart.addCandlestickSeries({
      upColor: "#26dad2",
      downColor: "#ef5350",
      borderDownColor: "#ef5350",
      borderUpColor: "#26dad2",
      wickDownColor: "#ef5350",
      wickUpColor: "#26dad2",
    });

    // 거래량 히스토그램
    const volumeSeries = chart.addHistogramSeries({
      color: "#26a69a",
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    // 예측 경로 (파란색 점선)
    const predLine = chart.addLineSeries({
      color: "#4680ff",
      lineWidth: 2,
      lineStyle: 2, // Dashed
      crosshairMarkerVisible: false,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    // 상한선 (반투명)
    const predUpper = chart.addLineSeries({
      color: "rgba(70, 128, 255, 0.25)",
      lineWidth: 1,
      lineStyle: 1, // Dotted
      crosshairMarkerVisible: false,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    // 하한선 (반투명)
    const predLower = chart.addLineSeries({
      color: "rgba(70, 128, 255, 0.25)",
      lineWidth: 1,
      lineStyle: 1,
      crosshairMarkerVisible: false,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    // 실제 경로 (검증 후 금색 실선)
    const actualLine = chart.addLineSeries({
      color: "#ffb22b",
      lineWidth: 2,
      lineStyle: 0, // Solid
      crosshairMarkerVisible: false,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    predLineRef.current = predLine;
    predUpperRef.current = predUpper;
    predLowerRef.current = predLower;
    actualLineRef.current = actualLine;

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, []);

  // 캔들 데이터 업데이트
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || !candles.length) return;

    const tzOffsetSec = -new Date().getTimezoneOffset() * 60;

    const candleData: CandlestickData[] = candles.map((c) => ({
      time: (c.time + tzOffsetSec) as any,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    const volumeData: HistogramData[] = candles.map((c) => ({
      time: (c.time + tzOffsetSec) as any,
      value: c.volume,
      color: c.close >= c.open ? "rgba(38,218,210,0.3)" : "rgba(239,83,80,0.3)",
    }));

    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current.setData(volumeData);

    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  // 예측 데이터 업데이트
  useEffect(() => {
    if (!predLineRef.current || !predUpperRef.current || !predLowerRef.current || !actualLineRef.current) return;

    if (!prediction || !prediction.predicted_path?.length) {
      predLineRef.current.setData([]);
      predUpperRef.current.setData([]);
      predLowerRef.current.setData([]);
      actualLineRef.current.setData([]);
      return;
    }

    const tzOffsetSec = -new Date().getTimezoneOffset() * 60;

    const mapPath = (path: PredictionPoint[]): LineData[] =>
      path.map((p) => ({
        time: (p.time + tzOffsetSec) as any,
        value: p.price,
      }));

    predLineRef.current.setData(mapPath(prediction.predicted_path));
    predUpperRef.current.setData(mapPath(prediction.upper_bound_path));
    predLowerRef.current.setData(mapPath(prediction.lower_bound_path));

    if (prediction.actual_path?.length) {
      actualLineRef.current.setData(mapPath(prediction.actual_path));
    } else {
      actualLineRef.current.setData([]);
    }
  }, [prediction]);

  // TP/SL 수평선 오버레이
  useEffect(() => {
    if (!candleSeriesRef.current) return;

    // 기존 라인 제거
    for (const line of priceLinesRef.current) {
      try {
        candleSeriesRef.current.removePriceLine(line);
      } catch {
        // 이미 제거된 경우 무시
      }
    }
    priceLinesRef.current = [];

    if (!prediction || prediction.status !== "ACTIVE") return;

    const lines: { price: number; title: string; color: string }[] = [
      { price: prediction.entry_price, title: "Entry", color: "#4680ff" },
      { price: prediction.stop_loss, title: "SL", color: "#ef5350" },
      { price: prediction.take_profit_1, title: "TP1", color: "#26dad2" },
      { price: prediction.take_profit_2, title: "TP2", color: "#26dad2" },
      { price: prediction.take_profit_3, title: "TP3", color: "#26dad2" },
    ];

    for (const { price, title, color } of lines) {
      if (!price) continue;
      const priceLine = candleSeriesRef.current.createPriceLine({
        price,
        color,
        lineWidth: 1,
        lineStyle: 2, // Dashed
        axisLabelVisible: true,
        title,
      });
      priceLinesRef.current.push(priceLine);
    }
  }, [prediction]);

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="px-4 py-2 bg-card border-b border-border flex items-center justify-between">
        <span className="font-medium">{symbol}</span>
        {prediction && (
          <div className="flex items-center gap-2 text-xs">
            <span className="w-3 h-0.5 inline-block" style={{ borderTop: "2px dashed #4680ff", backgroundColor: "#4680ff" }} />
            <span style={{ color: "#4680ff" }}>예측</span>
            {prediction.actual_path && (
              <>
                <span className="w-3 h-0.5 inline-block" style={{ backgroundColor: "#ffb22b" }} />
                <span style={{ color: "#ffb22b" }}>실제</span>
              </>
            )}
          </div>
        )}
      </div>
      <div ref={containerRef} />
    </div>
  );
}
