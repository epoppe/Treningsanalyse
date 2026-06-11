"use client";

import { Card, Text } from '@tremor/react';
import dynamic from 'next/dynamic';
import type { AsyncLoadState } from '@/utils/metricState';

const PlotlyChart = dynamic(() => import('@/components/PlotlyChart'), {
  ssr: false,
  loading: () => <Text>Laster graf...</Text>,
});

interface ActivityDetailsChartsProps {
  detailsState: AsyncLoadState;
  detailsData: Record<string, unknown>[];
}

const ActivityDetailsCharts = ({ detailsState, detailsData }: ActivityDetailsChartsProps) => {
  if (detailsState === 'missing') {
    return (
      <Card className="mt-6">
        <Text>Ingen tidsseriedata (FIT-detaljer) tilgjengelig for denne aktiviteten.</Text>
      </Card>
    );
  }

  if (detailsState !== 'ready') {
    return null;
  }

  return (
    <>
      <Card className="mt-6">
        <div className="h-96">
          <PlotlyChart
            data={detailsData}
            xKey="timestamp"
            yKeys={['heart_rate']}
            title="Puls over tid"
            yAxisTitle="Puls (bpm)"
          />
        </div>
      </Card>

      <Card className="mt-6">
        <div className="h-96">
          <PlotlyChart
            data={detailsData}
            xKey="elapsed_time"
            yKeys={['speed']}
            title="Fart over tid"
            yAxisTitle="Fart (km/t)"
          />
        </div>
      </Card>

      <Card className="mt-6">
        <div className="h-96">
          <PlotlyChart
            data={detailsData}
            xKey="timestamp"
            yKeys={['altitude']}
            title="Høydeprofil"
            yAxisTitle="Høydemeter (moh)"
          />
        </div>
      </Card>
    </>
  );
};

export default ActivityDetailsCharts;
