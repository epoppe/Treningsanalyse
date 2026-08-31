"use client";

import dynamic from "next/dynamic";
import type { AsyncLoadState } from "@/utils/metricState";
import { ChartShell } from "@/components/charts/ChartShell";

const PlotlyChart = dynamic(() => import("@/components/PlotlyChart"), {
  ssr: false,
  loading: () => (
    <p className="flex h-full items-center justify-center text-sm text-slate-500">
      Laster graf...
    </p>
  ),
});

interface ActivityDetailsChartsProps {
  detailsState: AsyncLoadState;
  detailsData: Record<string, unknown>[];
}

const ActivityDetailsCharts = ({
  detailsState,
  detailsData,
}: ActivityDetailsChartsProps) => {
  if (detailsState === "missing") {
    return (
      <ChartShell title="Øktdetaljer" isEmpty emptyMessage="Ingen tidsseriedata (FIT-detaljer) tilgjengelig for denne aktiviteten." />
    );
  }

  if (detailsState !== "ready") {
    return null;
  }

  return (
    <div className="mt-4 space-y-4">
      <ChartShell title="Puls over tid" heightClassName="h-96">
        <PlotlyChart
          data={detailsData}
          xKey="timestamp"
          yKeys={["heart_rate"]}
          title="Puls over tid"
          yAxisTitle="Puls (bpm)"
        />
      </ChartShell>

      <ChartShell title="Fart over tid" heightClassName="h-96">
        <PlotlyChart
          data={detailsData}
          xKey="elapsed_time"
          yKeys={["speed"]}
          title="Fart over tid"
          xAxisTitle="Tid (sek)"
          yAxisTitle="Fart (km/t)"
        />
      </ChartShell>

      <ChartShell title="Høydeprofil" heightClassName="h-96">
        <PlotlyChart
          data={detailsData}
          xKey="timestamp"
          yKeys={["altitude"]}
          title="Høydeprofil"
          yAxisTitle="Høydemeter (moh)"
        />
      </ChartShell>
    </div>
  );
};

export default ActivityDetailsCharts;
