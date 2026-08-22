"use client";

import dynamic from "next/dynamic";
import { Text } from "@tremor/react";
import { buildPlotlyLayout, buildPlotlyTraces } from "@/components/charts/plotlyTheme";

const Plot = dynamic<any>(() => import("react-plotly.js"), {
  ssr: false,
});

interface PlotlyChartProps {
  data: Record<string, unknown>[];
  xKey: string;
  yKeys: string[];
  title: string;
  yAxisTitle: string;
  xAxisTitle?: string;
  traceMode?: "lines+markers" | "markers" | "lines";
  textKey?: string;
}

const PlotlyChart = ({
  data,
  xKey,
  yKeys,
  title,
  yAxisTitle,
  xAxisTitle = "Dato",
  traceMode = "lines+markers",
  textKey,
}: PlotlyChartProps) => {
  if (!data || data.length === 0) {
    return <Text>Ingen data tilgjengelig for å vise grafen.</Text>;
  }

  const traces = buildPlotlyTraces({
    data,
    xKey,
    yKeys,
    traceMode,
    textKey,
    xAxisTitle,
    yAxisTitle,
  });

  const layout = buildPlotlyLayout({ title, xAxisTitle, yAxisTitle });

  return (
    <Plot
      data={traces}
      layout={layout}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
      config={{ displayModeBar: false, responsive: true }}
    />
  );
};

export default PlotlyChart;
