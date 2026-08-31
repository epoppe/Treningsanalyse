import { PLOTLY_TRACE_LABELS } from "@/lib/metrics";
import { CHART_AXIS, CHART_GRID, CHART_PRIMARY, chartColor } from "./chartTheme";

function humanizeTraceName(yKey: string): string {
  if (PLOTLY_TRACE_LABELS[yKey]) return PLOTLY_TRACE_LABELS[yKey];
  return yKey.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
}

export function buildPlotlyLayout({
  title,
  xAxisTitle = "Dato",
  yAxisTitle,
  height,
}: {
  title: string;
  xAxisTitle?: string;
  yAxisTitle: string;
  height?: number;
}) {
  return {
    title: {
      text: title,
      font: { size: 14, color: "#0f172a" },
    },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    font: { family: "inherit", color: "#475569", size: 11 },
    xaxis: {
      title: xAxisTitle,
      gridcolor: CHART_GRID.stroke,
      linecolor: CHART_AXIS.stroke,
      tickfont: { size: 10, color: CHART_AXIS.tick.fill },
    },
    yaxis: {
      title: yAxisTitle,
      gridcolor: CHART_GRID.stroke,
      linecolor: CHART_AXIS.stroke,
      tickfont: { size: 10, color: CHART_AXIS.tick.fill },
    },
    autosize: true,
    margin: { l: 50, r: 24, b: 48, t: 48, pad: 4 },
    ...(height ? { height } : {}),
  };
}

export function buildPlotlyTraces({
  data,
  xKey,
  yKeys,
  traceMode = "lines+markers",
  textKey,
  xAxisTitle = "Dato",
  yAxisTitle,
}: {
  data: Record<string, unknown>[];
  xKey: string;
  yKeys: string[];
  traceMode?: "lines+markers" | "markers" | "lines";
  textKey?: string;
  xAxisTitle?: string;
  yAxisTitle: string;
}) {
  const hoverTemplate = textKey
    ? `%{text}<br>${xAxisTitle}: %{x}<br>${yAxisTitle}: %{y}<extra></extra>`
    : undefined;

  return yKeys.map((yKey, index) => ({
    x: data.map((item) => item[xKey]),
    y: data.map((item) => item[yKey]),
    name: humanizeTraceName(yKey),
    type: "scatter" as const,
    mode: traceMode,
    line: { color: index === 0 ? CHART_PRIMARY : chartColor(index), width: 2 },
    marker: { color: index === 0 ? CHART_PRIMARY : chartColor(index), size: 6 },
    ...(textKey
      ? {
          text: data.map((item) => String(item[textKey] ?? "")),
          hovertemplate: hoverTemplate,
        }
      : {}),
  }));
}
