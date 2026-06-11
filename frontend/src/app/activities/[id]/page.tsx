"use client";

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { Card, Title, Text } from '@tremor/react';
import ActivityAnalytics from '@/components/ActivityAnalytics';
import ActivityDetailsCharts from '@/components/ActivityDetailsCharts';
import type { AsyncLoadState } from '@/utils/metricState';

const ActivityDetailPage = () => {
    const params = useParams();
    const id = Number(params.id);
    const [detailsState, setDetailsState] = useState<AsyncLoadState>('loading');
    const [detailsData, setDetailsData] = useState<Record<string, unknown>[]>([]);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!id || Number.isNaN(id)) return;

        const controller = new AbortController();

        const fetchDetails = async () => {
            setDetailsState('loading');
            setError(null);

            try {
                const response = await fetch(`/api/activities/${id}/details`, {
                    signal: controller.signal,
                });

                if (response.status === 404) {
                    setDetailsData([]);
                    setDetailsState('missing');
                    return;
                }

                if (!response.ok) {
                    throw new Error(`API-feil (${response.status}): ${response.statusText}`);
                }

                const data = await response.json();
                if (!Array.isArray(data) || data.length === 0) {
                    setDetailsData([]);
                    setDetailsState('missing');
                    return;
                }

                setDetailsData(data);
                setDetailsState('ready');
            } catch (err) {
                if (controller.signal.aborted) {
                    return;
                }
                setDetailsState('error');
                if (err instanceof Error) {
                    setError(err.message);
                } else {
                    setError('En ukjent feil oppstod ved henting av aktivitetsdetaljer');
                }
            }
        };

        void fetchDetails();

        return () => controller.abort();
    }, [id]);

    if (Number.isNaN(id)) {
        return <Text>Ugyldig aktivitets-ID.</Text>;
    }

    if (detailsState === 'loading') {
        return <Text>Laster aktivitetsdetaljer...</Text>;
    }

    if (detailsState === 'error') {
        return (
            <main className="p-4 md:p-10 mx-auto max-w-7xl">
                <Title>Aktivitetsdetaljer</Title>
                <Card className="mt-6">
                    <Text className="text-red-600">Feil ved henting av aktivitetsdetaljer: {error}</Text>
                </Card>
                <div className="mt-6">
                    <ActivityAnalytics activityId={id} />
                </div>
            </main>
        );
    }

    return (
        <main className="p-4 md:p-10 mx-auto max-w-7xl">
            <Title>Aktivitetsdetaljer</Title>

            <div className="mt-6">
                <ActivityAnalytics activityId={id} />
            </div>

            <ActivityDetailsCharts detailsState={detailsState} detailsData={detailsData} />
        </main>
    );
};

export default ActivityDetailPage;
