"use client";

import {
  Area,
  ComposedChart,
  Line,
  ResponsiveContainer,
} from "recharts";
import {
  CHART_MARGIN,
  LEGACY_SERIES_COLORS,
} from "@/components/charts/chartTheme";
import {
  ThemedCartesianGrid,
  ThemedLegend,
  ThemedTooltip,
  ThemedXAxis,
  ThemedYAxis,
} from "@/components/charts/ThemedRecharts";
import { ChartShell } from "@/components/charts/ChartShell";

export interface TrainingStressDailyPoint {
  date: string;
  ctl: number;
  atl: number;
  tss: number;
  form: number;
}

function formatChartDate(dateString: string) {
  const date = new Date(dateString);
  return date.toLocaleDateString("nb-NO", { month: "short", day: "numeric", year: "numeric" });
}

function formatTooltipDate(dateString: string) {
  const date = new Date(dateString);
  return date.toLocaleDateString("nb-NO", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function TrainingLoadChart({ data }: { data: TrainingStressDailyPoint[] }) {
  const rows = data.map((day) => ({
    ...day,
    label: formatChartDate(day.date),
  }));

  return (
    <ChartShell title="Training Load (CTL/ATL/TSS) Over Tid" heightClassName="h-[360px]">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={CHART_MARGIN.labeled}>
          <ThemedCartesianGrid vertical={false} />
          <ThemedXAxis dataKey="label" minTickGap={28} />
          <ThemedYAxis />
          <ThemedTooltip
            labelFormatter={(_, payload) =>
              payload?.[0]?.payload?.date
                ? formatTooltipDate(String(payload[0].payload.date))
                : ""
            }
          />
          <ThemedLegend />
          <Area
            type="monotone"
            dataKey="ctl"
            name="CTL"
            stroke={LEGACY_SERIES_COLORS.ctl}
            fill={`${LEGACY_SERIES_COLORS.ctl}33`}
            strokeWidth={2}
            dot={false}
          />
          <Area
            type="monotone"
            dataKey="atl"
            name="ATL"
            stroke={LEGACY_SERIES_COLORS.atl}
            fill={`${LEGACY_SERIES_COLORS.atl}33`}
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="tss"
            name="TSS"
            stroke={LEGACY_SERIES_COLORS.tss}
            strokeWidth={2}
            dot={{ r: 3, fill: LEGACY_SERIES_COLORS.tss }}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}

export function TrainingFormChart({ data }: { data: TrainingStressDailyPoint[] }) {
  const rows = data.map((day) => ({
    ...day,
    label: formatChartDate(day.date),
  }));

  return (
    <ChartShell title="Form (Fitness/Fatigue) Over Tid" heightClassName="h-[320px]">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={CHART_MARGIN.labeled}>
          <ThemedCartesianGrid vertical={false} />
          <ThemedXAxis dataKey="label" minTickGap={28} />
          <ThemedYAxis />
          <ThemedTooltip
            labelFormatter={(_, payload) =>
              payload?.[0]?.payload?.date
                ? formatTooltipDate(String(payload[0].payload.date))
                : ""
            }
            formatter={(value: any) => {
              const numeric = Number(value);
              let status = " (Tretthet)";
              if (numeric >= 10) status = " (God form)";
              else if (numeric >= 0) status = " (Nøytral)";
              return [`Form: ${numeric.toFixed(1)}${status}`, "Form"];
            }}
          />
          <ThemedLegend />
          <Area
            type="monotone"
            dataKey="form"
            name="Form"
            stroke={LEGACY_SERIES_COLORS.form}
            fill={`${LEGACY_SERIES_COLORS.form}33`}
            strokeWidth={2}
            dot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}
