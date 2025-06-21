"use client";

import { useState } from 'react';
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

    if (isNaN(id)) {
        return <Text>Ugyldig aktivitets-ID.</Text>;
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