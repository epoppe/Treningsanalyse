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
import {
  axisLabelProps,
  formatChartAxisDate,
  formatChartTooltipDate,
  formatWithUnit,
} from "@/lib/chartFormatters";
import { getMetricDefinition } from "@/lib/metrics";

export interface TrainingStressDailyPoint {
  date: string;
  ctl: number;
  atl: number;
  tss: number;
  form: number;
}

const loadDef = getMetricDefinition("ctl");
const formDef = getMetricDefinition("form");

function formatChartDate(dateString: string) {
  return formatChartAxisDate(dateString, "dayMonthYear");
}

export function TrainingLoadChart({ data }: { data: TrainingStressDailyPoint[] }) {
  const rows = data.map((day) => ({
    ...day,
    label: formatChartDate(day.date),
  }));

  return (
    <ChartShell
      title="Treningsbelastning over tid"
      subtitle="CTL (kronisk), ATL (akutt) og TSS (dagsbelastning)"
      heightClassName="h-[360px]"
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={CHART_MARGIN.labeled}>
          <ThemedCartesianGrid vertical={false} />
          <ThemedXAxis dataKey="label" minTickGap={28} />
          <ThemedYAxis label={axisLabelProps(loadDef.axisLabel)} width={48} />
          <ThemedTooltip
            labelFormatter={(_, payload) =>
              payload?.[0]?.payload?.date
                ? formatChartTooltipDate(String(payload[0].payload.date))
                : ""
            }
            formatter={(value: number, name: string) => {
              const labels: Record<string, string> = {
                ctl: "CTL (kronisk belastning)",
                atl: "ATL (akutt belastning)",
                tss: "TSS (dagsbelastning)",
              };
              return [
                formatWithUnit(Number(value), loadDef.unit, 1),
                labels[name] || name,
              ];
            }}
          />
          <ThemedLegend />
          <Area
            type="monotone"
            dataKey="ctl"
            name="CTL (kronisk belastning)"
            stroke={LEGACY_SERIES_COLORS.ctl}
            fill={`${LEGACY_SERIES_COLORS.ctl}33`}
            strokeWidth={2}
            dot={false}
          />
          <Area
            type="monotone"
            dataKey="atl"
            name="ATL (akutt belastning)"
            stroke={LEGACY_SERIES_COLORS.atl}
            fill={`${LEGACY_SERIES_COLORS.atl}33`}
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="tss"
            name="TSS (dagsbelastning)"
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
    <ChartShell
      title="Form over tid"
      subtitle="Form = CTL − ATL · positiv = overskudd, negativ = tretthet"
      heightClassName="h-[320px]"
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={CHART_MARGIN.labeled}>
          <ThemedCartesianGrid vertical={false} />
          <ThemedXAxis dataKey="label" minTickGap={28} />
          <ThemedYAxis label={axisLabelProps(formDef.axisLabel)} width={48} />
          <ThemedTooltip
            labelFormatter={(_, payload) =>
              payload?.[0]?.payload?.date
                ? formatChartTooltipDate(String(payload[0].payload.date))
                : ""
            }
            formatter={(value: number) => {
              const numeric = Number(value);
              let status = " (tretthet)";
              if (numeric >= 10) status = " (god form)";
              else if (numeric >= 0) status = " (nøytral)";
              return [
                `${formatWithUnit(numeric, formDef.unit, 1)}${status}`,
                formDef.displayName,
              ];
            }}
          />
          <ThemedLegend />
          <Area
            type="monotone"
            dataKey="form"
            name="Form (CTL − ATL)"
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
