import React, { useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts";

type ChartSeries = {
  name: string;
  data: Array<number | null>;
};

type ScatterPoint = [number, number];

export type XlsxTraceChartSpec = {
  chart_type?: string;
  title?: string;
  title_zh?: string;
  description?: string;
  description_zh?: string;
  trend_summary?: string;
  trend_summary_zh?: string;
  x_field?: string;
  y_fields?: string[];
  x_axis_label?: string;
  y_axis_label?: string;
  x_values?: string[];
  series?: ChartSeries[];
  points?: ScatterPoint[];
  x_domain?: number[] | [number, number];
  y_domain?: number[] | [number, number];
  point_count?: number;
  aggregation?: string;
};

type XlsxTraceChartProps = {
  spec: XlsxTraceChartSpec;
  className?: string;
};

const CHART_PALETTES: string[][] = [
  ["#0f766e", "#1d4ed8", "#ea580c", "#4338ca", "#0891b2"],
  ["#16a34a", "#0284c7", "#f97316", "#7c3aed", "#db2777"],
  ["#2563eb", "#0d9488", "#e11d48", "#ca8a04", "#7c3aed"],
  ["#0891b2", "#4f46e5", "#d97706", "#059669", "#be185d"],
  ["#1d4ed8", "#0284c7", "#0f766e", "#ea580c", "#9333ea"],
];

const clampNumber = (value: unknown): number | null => {
  if (value === null || value === undefined) return null;
  if (typeof value === "string" && value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const hashText = (raw: string): number => {
  let hash = 2166136261;
  for (let i = 0; i < raw.length; i += 1) {
    hash ^= raw.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0);
};

const hexToRgb = (hex: string): [number, number, number] | null => {
  const normalized = String(hex || "").trim();
  const full = normalized.startsWith("#") ? normalized.slice(1) : normalized;
  if (!/^[0-9a-fA-F]{6}$/.test(full)) return null;
  const num = Number.parseInt(full, 16);
  return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
};

const withAlpha = (hex: string, alpha: number): string => {
  const rgb = hexToRgb(hex);
  if (!rgb) return hex;
  const safeAlpha = Math.max(0, Math.min(1, alpha));
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${safeAlpha})`;
};

const resolvePalette = (spec: XlsxTraceChartSpec): string[] => {
  const fingerprint = [
    spec.chart_type,
    spec.title,
    spec.x_field,
    ...(Array.isArray(spec.y_fields) ? spec.y_fields : []),
  ]
    .map((item) => String(item || "").trim().toLowerCase())
    .filter(Boolean)
    .join("|");
  const paletteIndex = hashText(fingerprint || "default") % CHART_PALETTES.length;
  return CHART_PALETTES[paletteIndex];
};

const normalizeSeries = (value: unknown): ChartSeries[] => {
  if (!Array.isArray(value)) return [];
  return value
    .map((item, idx) => {
      if (!item || typeof item !== "object") return null;
      const row = item as Record<string, unknown>;
      const name = String(row.name ?? `series_${idx + 1}`).trim() || `series_${idx + 1}`;
      const rawData = Array.isArray(row.data) ? row.data : [];
      const data = rawData.map((cell) => clampNumber(cell));
      const hasAnyFinite = data.some((cell) => typeof cell === "number");
      return hasAnyFinite ? { name, data } : null;
    })
    .filter((item): item is ChartSeries => !!item);
};

const normalizeScatterPoints = (value: unknown): ScatterPoint[] => {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (!Array.isArray(item) || item.length < 2) return null;
      const x = clampNumber(item[0]);
      const y = clampNumber(item[1]);
      if (x === null || y === null) return null;
      return [x, y] as ScatterPoint;
    })
    .filter((item): item is ScatterPoint => !!item);
};

const resolveAxisLabel = (primary?: string, fallback?: string): string => {
  const first = String(primary ?? "").trim();
  if (first) return first;
  return String(fallback ?? "").trim();
};

const truncateTickLabel = (raw: string, maxLen: number): string => {
  const text = String(raw ?? "").trim();
  if (!text) return "";
  if (text.length <= maxLen) return text;
  return `${text.slice(0, Math.max(3, maxLen - 1))}…`;
};

const quantile = (values: number[], q: number): number | null => {
  if (!Array.isArray(values) || values.length === 0) return null;
  const ordered = [...values].filter(Number.isFinite).sort((a, b) => a - b);
  if (ordered.length === 0) return null;
  if (ordered.length === 1) return ordered[0];
  const safeQ = Math.max(0, Math.min(1, q));
  const pos = safeQ * (ordered.length - 1);
  const low = Math.floor(pos);
  const high = Math.min(low + 1, ordered.length - 1);
  const ratio = pos - low;
  if (high === low) return ordered[low];
  return ordered[low] * (1 - ratio) + ordered[high] * ratio;
};

const parseNumericDomain = (raw: unknown): [number, number] | null => {
  if (!Array.isArray(raw) || raw.length < 2) return null;
  const min = clampNumber(raw[0]);
  const max = clampNumber(raw[1]);
  if (min === null || max === null) return null;
  if (max <= min) return null;
  return [min, max];
};

const buildNumericDomain = (
  values: number[],
  opts?: { lowQ?: number; highQ?: number; padRatio?: number }
): [number, number] | null => {
  const finite = values.filter(Number.isFinite);
  if (finite.length === 0) return null;
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

const buildChartOption = (spec: XlsxTraceChartSpec): echarts.EChartsOption | null => {
  const chartType = String(spec.chart_type ?? "").trim().toLowerCase();
  const xValues = Array.isArray(spec.x_values)
    ? spec.x_values.map((item) => String(item ?? "").trim())
    : [];
  const series = normalizeSeries(spec.series);
  const scatterPoints = normalizeScatterPoints(spec.points);
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

  if ((chartType === "line" || chartType === "bar") && xValues.length > 0 && series.length > 0) {
    const isLine = chartType === "line";
    const yValues = series.flatMap((item) => item.data).filter((cell): cell is number => typeof cell === "number");
    const yDomain = buildNumericDomain(yValues, { lowQ: 0.03, highQ: 0.97, padRatio: 0.08 });
    const xLabelMaxLen = xValues.length > 48 ? 8 : xValues.length > 24 ? 10 : 14;
    const shouldRotateX = xValues.length > 16;
    return {
      animationDuration: 520,
      animationDurationUpdate: 420,
      color: palette,
      grid: { top: 30, right: 18, bottom: xAxisLabel ? 58 : 42, left: 62, containLabel: true },
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
        nameGap: yAxisLabel ? 46 : 30,
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
                height: 12,
                bottom: 8,
                borderColor: "rgba(148,163,184,0.35)",
                fillerColor: "rgba(37,99,235,0.2)",
              },
            ]
          : undefined,
      series: series.map((item, idx) => {
        const color = palette[idx % palette.length];
        if (isLine) {
          return {
            name: item.name,
            type: "line",
            data: item.data,
            smooth: true,
            showSymbol: xValues.length <= 16,
            symbol: "circle",
            symbolSize: 6,
            lineStyle: { width: 2.2, color },
            itemStyle: { color, borderColor: "#ffffff", borderWidth: 1 },
            areaStyle:
              idx === 0
                ? {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                      { offset: 0, color: withAlpha(color, 0.26) },
                      { offset: 1, color: withAlpha(color, 0.02) },
                    ]),
                  }
                : undefined,
          };
        }
        return {
          name: item.name,
          type: "bar",
          data: item.data,
          barMaxWidth: 34,
          itemStyle: {
            borderRadius: [7, 7, 2, 2],
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: withAlpha(color, 0.96) },
              { offset: 1, color: withAlpha(color, 0.58) },
            ]),
          },
        };
      }),
    };
  }

  if (chartType === "pie" && series.length > 0 && xValues.length > 0) {
    const values = series[0].data;
    const pieData = xValues
      .map((name, idx) => ({ name, value: values[idx] ?? 0 }))
      .filter((item) => Number.isFinite(item.value) && Number(item.value) > 0);
    if (pieData.length === 0) return null;
    return {
      animationDuration: 520,
      color: palette,
      tooltip: { trigger: "item" },
      legend: { bottom: 0, textStyle: { fontSize: 11, color: "#334155" } },
      series: [
        {
          type: "pie",
          radius: ["38%", "70%"],
          center: ["50%", "44%"],
          avoidLabelOverlap: true,
          data: pieData,
          label: { fontSize: 10, color: "#334155", formatter: "{b}: {d}%" },
          labelLine: { length: 10, length2: 8 },
          itemStyle: {
            borderColor: "rgba(255,255,255,0.95)",
            borderWidth: 1.2,
          },
          emphasis: {
            scale: true,
            itemStyle: {
              shadowBlur: 18,
              shadowColor: "rgba(15,23,42,0.25)",
            },
          },
        },
      ],
    };
  }

  if (chartType === "scatter" && scatterPoints.length > 0) {
    const xValues = scatterPoints.map((item) => item[0]);
    const yValues = scatterPoints.map((item) => item[1]);
    const domainFromSpecX = parseNumericDomain(spec.x_domain);
    const domainFromSpecY = parseNumericDomain(spec.y_domain);
    const xDomain = domainFromSpecX ?? buildNumericDomain(xValues, { lowQ: 0.02, highQ: 0.98, padRatio: 0.06 });
    const yDomain = domainFromSpecY ?? buildNumericDomain(yValues, { lowQ: 0.02, highQ: 0.98, padRatio: 0.06 });
    const yMin = yDomain ? yDomain[0] : Math.min(...yValues);
    const yMax = yDomain ? yDomain[1] : Math.max(...yValues);
    const startColor = palette[0] || "#2563eb";
    const endColor = palette[2] || "#ea580c";
    return {
      animationDuration: 480,
      grid: { top: 24, right: 16, bottom: xAxisLabel ? 58 : 38, left: 62, containLabel: true },
      tooltip: { trigger: "item" },
      xAxis: {
        ...axisCommon,
        type: "value",
        name: xAxisLabel || undefined,
        nameGap: xAxisLabel ? 36 : 22,
        scale: true,
        min: xDomain ? xDomain[0] : undefined,
        max: xDomain ? xDomain[1] : undefined,
      },
      yAxis: {
        ...axisCommon,
        type: "value",
        name: yAxisLabel || undefined,
        nameGap: yAxisLabel ? 46 : 30,
        nameRotate: 90,
        scale: true,
        min: yDomain ? yDomain[0] : undefined,
        max: yDomain ? yDomain[1] : undefined,
      },
      visualMap: {
        min: yMin,
        max: yMax,
        dimension: 1,
        show: false,
        inRange: {
          color: [withAlpha(startColor, 0.55), withAlpha(endColor, 0.95)],
          symbolSize: [7, 16],
        },
      },
      series: [
        {
          type: "scatter",
          data: scatterPoints,
          large: scatterPoints.length > 400,
          progressive: 800,
          emphasis: { scale: true },
          symbolSize: scatterPoints.length > 220 ? 7 : 9,
          itemStyle: {
            borderColor: "rgba(255,255,255,0.8)",
            borderWidth: 0.8,
          },
        },
      ],
    };
  }

  return null;
};

export const XlsxTraceChart: React.FC<XlsxTraceChartProps> = ({ spec, className }) => {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const option = useMemo(() => buildChartOption(spec), [spec]);

  useEffect(() => {
    const root = rootRef.current;
    if (!root || !option) return;

    const chart = echarts.init(root, undefined, { renderer: "canvas" });
    chartRef.current = chart;
    chart.setOption(option, { notMerge: true, lazyUpdate: false });

    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => chart.resize())
        : null;
    observer?.observe(root);

    return () => {
      observer?.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, [option]);

  if (!option) {
    return (
      <div
        className={className}
        style={{
          minHeight: 220,
          borderRadius: 10,
          border: "1px dashed rgba(100,116,139,0.35)",
          background:
            "linear-gradient(165deg, rgba(248,250,252,0.92) 0%, rgba(241,245,249,0.88) 100%)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 12,
          color: "#64748b",
        }}
      >
        No chart data available
      </div>
    );
  }

  return (
    <div
      ref={rootRef}
      className={className}
      style={{
        width: "100%",
        minHeight: 240,
      }}
    />
  );
};
