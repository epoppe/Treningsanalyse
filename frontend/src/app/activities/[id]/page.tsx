"use client";

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { Card, Title, Text } from '@tremor/react';
import dynamic from 'next/dynamic';

const PlotlyChart = dynamic(() => import('@/components/PlotlyChart'), {
    ssr: false,
    loading: () => <Text>Laster graf...</Text>
});

const ActivityDetailPage = () => {
    const params = useParams();
    const id = Number(params.id);
    const [detailsReady, setDetailsReady] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!id) return;

        const fetchDetails = async () => {
            try {
                const response = await fetch(`/api/activities/${id}/details`);
                if (!response.ok) {
                    throw new Error(`Klarte ikke hente detaljer: ${response.statusText}`);
                }
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

            <Card className="mt-6">
                <div className="h-96">
                   <PlotlyChart activityId={id} chartType="pulse" />
                </div>
            </Card>

            <Card className="mt-6">
                 <div className="h-96">
                    <PlotlyChart activityId={id} chartType="pace" />
                </div>
            </Card>

            <Card className="mt-6">
                <div className="h-96">
                    <PlotlyChart activityId={id} chartType="altitude" />
                </div>
            </Card>
        </main>
    );
};

export default ActivityDetailPage; 