import React, { useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts";
import { getTraceChartKind, type TraceChartSpec } from "../../shared/trace/chartSpec";

type TraceChartPreviewProps = {
  spec: TraceChartSpec | null;
  className?: string;
  compact?: boolean;
};

type ChartSeries = {
  name: string;
  data: Array<number | null>;
};

type ScatterPoint = [number, number];

const CHART_PALETTES: string[][] = [
  ["#0f766e", "#1d4ed8", "#ea580c", "#4338ca", "#0891b2"],
  ["#16a34a", "#0284c7", "#f97316", "#7c3aed", "#db2777"],
  ["#2563eb", "#0d9488", "#e11d48", "#ca8a04", "#7c3aed"],
  ["#0891b2", "#4f46e5", "#d97706", "#059669", "#be185d"],
  ["#1d4ed8", "#0284c7", "#0f766e", "#ea580c", "#9333ea"],
];

const toFinite = (value: unknown): number | null => {
  if (value === null || value === undefined) return null;
  if (typeof value === "string" && value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const quantile = (values: number[], q: number): number | null => {
  const finite = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!finite.length) return null;
  if (finite.length === 1) return finite[0];
  const safeQ = Math.max(0, Math.min(1, q));
  const pos = safeQ * (finite.length - 1);
  const low = Math.floor(pos);
  const high = Math.min(low + 1, finite.length - 1);
  const ratio = pos - low;
  if (high === low) return finite[low];
  return finite[low] * (1 - ratio) + finite[high] * ratio;
};

const parseDomain = (raw: unknown): [number, number] | null => {
  if (!Array.isArray(raw) || raw.length < 2) return null;
  const min = toFinite(raw[0]);
  const max = toFinite(raw[1]);
  if (min === null || max === null || max <= min) return null;
  return [min, max];
};

const buildDomain = (
  values: number[],
  opts?: { lowQ?: number; highQ?: number; padRatio?: number }
): [number, number] | null => {
  const finite = values.filter(Number.isFinite);
  if (!finite.length) return null;

  const fullMin = Math.min(...finite);
  const fullMax = Math.max(...finite);
  if (fullMax <= fullMin) {
    const pad = Math.max(1, Math.abs(fullMin) * 0.1);
    return [fullMin - pad, fullMax + pad];
  }

  const lowQ = opts?.lowQ ?? 0.02;
  const highQ = opts?.highQ ?? 0.98;
  const qMin = quantile(finite, lowQ) ?? fullMin;
  const qMax = quantile(finite, highQ) ?? fullMax;
  const robustMin = Math.min(qMin, qMax);
  const robustMax = Math.max(qMin, qMax);
  const fullSpan = fullMax - fullMin;
  const robustSpan = robustMax - robustMin;
  const useRobust = robustSpan > 0 && fullSpan / robustSpan >= 4;
  const baseMin = useRobust ? robustMin : fullMin;
  const baseMax = useRobust ? robustMax : fullMax;
  const span = Math.max(baseMax - baseMin, 1e-9);
  const pad = span * (opts?.padRatio ?? 0.06);
  return [baseMin - pad, baseMax + pad];
};

const hashText = (raw: string): number => {
  let hash = 2166136261;
  for (let i = 0; i < raw.length; i += 1) {
    hash ^= raw.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0);
};

const resolvePalette = (spec: TraceChartSpec | null): string[] => {
  const fingerprint = [
    spec?.chart_type,
    spec?.title,
    spec?.x_field,
    ...(Array.isArray(spec?.y_fields) ? spec!.y_fields! : []),
  ]
    .map((item) => String(item || "").trim().toLowerCase())
    .filter(Boolean)
    .join("|");
  const idx = hashText(fingerprint || "default") % CHART_PALETTES.length;
  return CHART_PALETTES[idx];
};

const normalizeSeries = (spec: TraceChartSpec | null): ChartSeries[] => {
  const list = Array.isArray(spec?.series) ? spec.series : [];
  return list
    .map((item, idx) => {
      const name = String(item?.name || spec?.y_fields?.[idx] || `series_${idx + 1}`).trim();
      const rawData = Array.isArray(item?.data) ? item.data : [];
      const data = rawData.map((cell) => toFinite(cell));
      const hasAnyFinite = data.some((cell) => typeof cell === "number");
      if (!hasAnyFinite) return null;
      return { name: name || `series_${idx + 1}`, data };
    })
    .filter((item): item is ChartSeries => !!item);
};

const normalizeScatterPoints = (spec: TraceChartSpec | null): ScatterPoint[] => {
  const points = Array.isArray(spec?.points) ? spec.points : [];
  return points
    .map((item) => {
      if (!Array.isArray(item) || item.length < 2) return null;
      const x = toFinite(item[0]);
      const y = toFinite(item[1]);
      if (x === null || y === null) return null;
      return [x, y] as ScatterPoint;
    })
    .filter((item): item is ScatterPoint => !!item);
};

const normalizeXValues = (spec: TraceChartSpec | null): string[] => {
  const values = Array.isArray(spec?.x_values) ? spec?.x_values : [];
  return values.map((item, idx) => {
    const text = String(item ?? "").trim();
    return text || String(idx + 1);
  });
};

const truncateTickLabel = (raw: string, maxLen: number): string => {
  const text = String(raw || "").trim();
  if (!text) return "";
  if (text.length <= maxLen) return text;
  return `${text.slice(0, Math.max(3, maxLen - 3))}...`;
};

const resolveAxisLabel = (primary?: string, fallback?: string): string => {
  const primaryText = String(primary ?? "").trim();
  if (primaryText) return primaryText;
  return String(fallback ?? "").trim();
};

const buildChartOption = (spec: TraceChartSpec | null): echarts.EChartsOption | null => {
  const kind = getTraceChartKind(spec);
  if (!spec || !kind) return null;

  const xValues = normalizeXValues(spec);
  const series = normalizeSeries(spec);
  const points = normalizeScatterPoints(spec);
  const xAxisLabel = resolveAxisLabel(spec.x_axis_label, spec.x_field);
  const yAxisLabel = resolveAxisLabel(
    spec.y_axis_label,
    Array.isArray(spec.y_fields) ? spec.y_fields.filter(Boolean).join(" / ") : ""
  );
  const palette = resolvePalette(spec);

  const axisCommon = {
    nameLocation: "middle" as const,
    nameTextStyle: { fontSize: 11, color: "#334155" },
    axisLabel: { fontSize: 10, color: "#64748b" },
    axisLine: { lineStyle: { color: "rgba(100,116,139,0.35)" } },
    splitLine: { lineStyle: { color: "rgba(148,163,184,0.14)" } },
  };

  if ((kind === "line" || kind === "bar") && xValues.length > 0 && series.length > 0) {
    const yValues = series.flatMap((item) => item.data).filter((item): item is number => typeof item === "number");
    const yDomain = buildDomain(yValues, { lowQ: 0.03, highQ: 0.97, padRatio: 0.08 });
    const xLabelMaxLen = xValues.length > 42 ? 8 : xValues.length > 22 ? 10 : 14;
    const shouldRotateX = xValues.length > 16;

    return {
      animationDuration: 420,
      animationDurationUpdate: 300,
      color: palette,
      grid: { top: 28, right: 12, bottom: xAxisLabel ? 62 : 44, left: 56, containLabel: true },
      legend: { top: 0, textStyle: { fontSize: 11, color: "#334155" } },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(15,23,42,0.92)",
        borderWidth: 0,
        textStyle: { color: "#e2e8f0", fontSize: 11 },
      },
      xAxis: {
        ...axisCommon,
        type: "category",
        data: xValues,
        name: xAxisLabel || undefined,
        nameGap: xAxisLabel ? 36 : 22,
        axisLabel: {
          ...(axisCommon.axisLabel as Record<string, unknown>),
          rotate: shouldRotateX ? 28 : 0,
          interval: "auto",
          formatter: (value: string) => truncateTickLabel(String(value ?? ""), xLabelMaxLen),
        },
      },
      yAxis: {
        ...axisCommon,
        type: "value",
        name: yAxisLabel || undefined,
        nameGap: yAxisLabel ? 44 : 30,
        nameRotate: 90,
        scale: true,
        min: yDomain ? yDomain[0] : undefined,
        max: yDomain ? yDomain[1] : undefined,
      },
      dataZoom:
        xValues.length > 24
          ? [
              { type: "inside", throttle: 80 },
              {
                type: "slider",
                height: 10,
                bottom: 8,
                borderColor: "rgba(148,163,184,0.35)",
                fillerColor: "rgba(37,99,235,0.2)",
              },
            ]
          : undefined,
      series: series.map((item, index) => ({
        name: item.name,
        type: kind,
        data: item.data,
        smooth: kind === "line",
        showSymbol: kind === "line" ? xValues.length <= 14 : undefined,
        symbolSize: 5,
        lineStyle: kind === "line" ? { width: 2.2 } : undefined,
        barMaxWidth: kind === "bar" ? 32 : undefined,
        itemStyle:
          kind === "bar"
            ? { borderRadius: [7, 7, 2, 2] }
            : {
                borderColor: "#ffffff",
                borderWidth: 1,
              },
        color: palette[index % palette.length],
      })),
    };
  }

  if (kind === "scatter" && points.length > 0) {
    const xVals = points.map((item) => item[0]);
    const yVals = points.map((item) => item[1]);
    const xDomain = parseDomain(spec.x_domain) ?? buildDomain(xVals, { lowQ: 0.02, highQ: 0.98, padRatio: 0.06 });
    const yDomain = parseDomain(spec.y_domain) ?? buildDomain(yVals, { lowQ: 0.02, highQ: 0.98, padRatio: 0.06 });

    return {
      animationDuration: 360,
      color: palette,
      grid: { top: 22, right: 12, bottom: xAxisLabel ? 60 : 42, left: 56, containLabel: true },
      tooltip: { trigger: "item" },
      xAxis: {
        ...axisCommon,
        type: "value",
        name: xAxisLabel || undefined,
        nameGap: xAxisLabel ? 34 : 22,
        scale: true,
        min: xDomain ? xDomain[0] : undefined,
        max: xDomain ? xDomain[1] : undefined,
      },
      yAxis: {
        ...axisCommon,
        type: "value",
        name: yAxisLabel || undefined,
        nameGap: yAxisLabel ? 44 : 30,
        nameRotate: 90,
        scale: true,
        min: yDomain ? yDomain[0] : undefined,
        max: yDomain ? yDomain[1] : undefined,
      },
      series: [
        {
          type: "scatter",
          data: points,
          symbolSize: points.length > 220 ? 7 : 9,
          large: points.length > 400,
          progressive: 800,
          emphasis: { scale: true },
          itemStyle: {
            borderColor: "rgba(255,255,255,0.85)",
            borderWidth: 0.8,
          },
        },
      ],
    };
  }

  return null;
};

export const TraceChartPreview: React.FC<TraceChartPreviewProps> = ({
  spec,
  className = "",
  compact = false,
}) => {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const option = useMemo(() => buildChartOption(spec), [spec]);
  const height = compact ? 220 : 260;

  useEffect(() => {
    const root = rootRef.current;
    if (!root || !option) return;

    const chart = echarts.init(root, undefined, { renderer: "canvas" });
    chartRef.current = chart;
    chart.setOption(option, { notMerge: true, lazyUpdate: false });

    const resize = () => chart.resize({ animation: { duration: 100 } });
    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => resize())
        : null;
    observer?.observe(root);

    window.addEventListener("resize", resize);
    const timerA = window.setTimeout(resize, 0);
    const timerB = window.setTimeout(resize, 220);

    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", resize);
      window.clearTimeout(timerA);
      window.clearTimeout(timerB);
      chart.dispose();
      chartRef.current = null;
    };
  }, [option]);

  if (!option) {
    return (
      <div
        className={`rounded-2xl border border-slate-200/70 bg-white/80 px-4 py-6 text-center text-[12px] text-slate-500 dark:border-white/[0.08] dark:bg-white/[0.03] dark:text-slate-400 ${className}`.trim()}
      >
        当前图表预览不可用
      </div>
    );
  }

  return (
    <div
      className={`overflow-hidden rounded-2xl border border-slate-200/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(248,250,252,0.92))] p-3 shadow-[0_10px_30px_rgba(15,23,42,0.05)] dark:border-white/[0.08] dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.88),rgba(15,23,42,0.7))] ${className}`.trim()}
    >
      <div ref={rootRef} style={{ width: "100%", height }} />
    </div>
  );
};

export default TraceChartPreview;
