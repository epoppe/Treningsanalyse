"use client";

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { Card, Title, Text } from '@tremor/react';
import dynamic from 'next/dynamic';
import ActivityAnalytics from '@/components/ActivityAnalytics';
import TrainingReadiness from '@/components/TrainingReadiness';

const PlotlyChart = dynamic(() => import('@/components/PlotlyChart'), {
    ssr: false,
    loading: () => <Text>Laster graf...</Text>
});

const ActivityDetailPage = () => {
    const params = useParams();
    const id = Number(params.id);
    const [detailsReady, setDetailsReady] = useState(false);
    const [detailsData, setDetailsData] = useState<any[]>([]);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!id) return;

        const fetchDetails = async () => {
            try {
                const response = await fetch(`/api/activities/${id}/details`);
                if (!response.ok) {
                    throw new Error(`Klarte ikke hente detaljer: ${response.statusText}`);
                }
                const data = await response.json();
                setDetailsData(data);
                // Dataene er nå hentet og lagret på serveren. Vi kan nå laste grafene.
                setDetailsReady(true);
            } catch (err) {
                if (err instanceof Error) {
                    setError(err.message);
                } else {
                    setError('En ukjent feil oppstod');
                }
            }
        };

        fetchDetails();
    }, [id]);

    if (isNaN(id)) {
        return <Text>Ugyldig aktivitets-ID.</Text>;
    }

    if (error) {
        return <Text>Feil: {error}</Text>;
    }

    if (!detailsReady) {
        return <Text>Laster aktivitetsdetaljer...</Text>;
    }
    
    return (
        <main className="p-4 md:p-10 mx-auto max-w-7xl">
            <Title>Aktivitetsdetaljer</Title>

            <div className="mt-6">
                <TrainingReadiness showDetails={true} />
            </div>

            <div className="mt-6">
                <ActivityAnalytics activityId={id} />
            </div>

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
        </main>
    );
};

export default ActivityDetailPage; 