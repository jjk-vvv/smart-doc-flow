export type TraceChartSeries = {
  name?: string;
  data?: unknown[];
};

export type TraceChartSpec = {
  chart_type?: string;
  title?: string;
  title_zh?: string;
  description?: string;
  description_zh?: string;
  x_field?: string;
  y_fields?: string[];
  x_values?: unknown[];
  series?: TraceChartSeries[];
  points?: unknown[];
  x_domain?: unknown[];
  y_domain?: unknown[];
  x_axis_label?: string;
  y_axis_label?: string;
  trend_summary?: string;
  trend_summary_zh?: string;
  point_count?: number;
  aggregation?: string;
};

export type TraceChartKind = "line" | "bar" | "scatter";

export type TraceChartDatum = Record<string, string | number | null>;

const CHART_KINDS = new Set<TraceChartKind>(["line", "bar", "scatter"]);

export const TRACE_CHART_PALETTE = [
  "#0F766E",
  "#2563EB",
  "#F97316",
  "#7C3AED",
  "#DC2626",
  "#16A34A",
];

const isRecord = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);

const toFiniteNumber = (value: unknown): number | null => {
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
};

export const getTraceChartSpec = (value: unknown): TraceChartSpec | null => {
  if (!isRecord(value)) return null;
  const chartType = String(value.chart_type || "").trim().toLowerCase();
  if (!CHART_KINDS.has(chartType as TraceChartKind)) return null;
  return value as TraceChartSpec;
};

export const getTraceChartKind = (spec: TraceChartSpec | null | undefined): TraceChartKind | null => {
  const raw = String(spec?.chart_type || "").trim().toLowerCase();
  return CHART_KINDS.has(raw as TraceChartKind) ? (raw as TraceChartKind) : null;
};

export const getTraceChartTitle = (spec: TraceChartSpec | null | undefined, fallback = ""): string =>
  String(spec?.title_zh || spec?.title || fallback || "").trim();

export const getTraceChartSummary = (spec: TraceChartSpec | null | undefined): string =>
  String(spec?.trend_summary_zh || spec?.description_zh || spec?.trend_summary || spec?.description || "").trim();

export const getTraceChartPointCount = (spec: TraceChartSpec | null | undefined): number => {
  const pointCount = Number(spec?.point_count || 0);
  if (Number.isFinite(pointCount) && pointCount > 0) {
    return Math.round(pointCount);
  }
  if (getTraceChartKind(spec) === "scatter") {
    return Array.isArray(spec?.points) ? spec.points.length : 0;
  }
  const firstSeries = Array.isArray(spec?.series) ? spec.series[0] : null;
  return Array.isArray(firstSeries?.data) ? firstSeries.data.length : 0;
};

export const buildTraceChartData = (spec: TraceChartSpec | null | undefined): TraceChartDatum[] => {
  const kind = getTraceChartKind(spec);
  if (!kind || !spec) return [];

  if (kind === "scatter") {
    const yKey = String(spec.y_fields?.[0] || "y").trim() || "y";
    return Array.isArray(spec.points)
      ? spec.points
          .map((point) => {
            if (!Array.isArray(point) || point.length < 2) return null;
            const x = toFiniteNumber(point[0]);
            const y = toFiniteNumber(point[1]);
            if (x == null || y == null) return null;
            return {
              x,
              [yKey]: y,
            };
          })
          .filter(Boolean) as TraceChartDatum[]
      : [];
  }

  const xValues = Array.isArray(spec.x_values) ? spec.x_values : [];
  const seriesList = Array.isArray(spec.series) ? spec.series : [];
  const maxLength = Math.max(
    xValues.length,
    ...seriesList.map((series) => (Array.isArray(series?.data) ? series.data.length : 0)),
    0,
  );

  return Array.from({ length: maxLength }, (_, index) => {
    const row: TraceChartDatum = {
      x: String(xValues[index] ?? index + 1),
    };
    seriesList.forEach((series, seriesIndex) => {
      const key = String(series?.name || spec.y_fields?.[seriesIndex] || `series_${seriesIndex + 1}`).trim();
      if (!key) return;
      row[key] = toFiniteNumber(series?.data?.[index]);
    });
    return row;
  });
};

export const getTraceChartSeriesKeys = (spec: TraceChartSpec | null | undefined): string[] => {
  const kind = getTraceChartKind(spec);
  if (!kind || !spec) return [];
  if (kind === "scatter") {
    const key = String(spec.y_fields?.[0] || "y").trim() || "y";
    return [key];
  }
  const seriesList = Array.isArray(spec.series) ? spec.series : [];
  return seriesList
    .map((series, index) => String(series?.name || spec.y_fields?.[index] || `series_${index + 1}`).trim())
    .filter(Boolean);
};
