"use client";

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Card, Title, AreaChart, Text } from '@tremor/react';

interface ActivityDetail {
    timestamp: string;
    latitude?: number;
    longitude?: number;
    altitude?: number;
    speed?: number;
    heart_rate?: number;
    cadence?: number;
}

const ActivityDetailPage = () => {
    const params = useParams();
    const { id } = params;
    
    const [details, setDetails] = useState<ActivityDetail[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (id) {
            const fetchDetails = async () => {
                try {
                    setLoading(true);
                    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
                    const response = await fetch(`${baseUrl}/api/activities/${id}/details`);
                    if (!response.ok) {
                        throw new Error(`Klarte ikke å hente data: ${response.statusText}`);
                    }
                    const data = await response.json();
                    setDetails(data);
                } catch (e: any) {
                    setError(e.message);
                } finally {
                    setLoading(false);
                }
            };
            fetchDetails();
        }
    }, [id]);

    if (loading) return <Text>Laster aktivitetsdetaljer...</Text>;
    if (error) return <Text>Feil: {error}</Text>;
    if (!details.length) return <Text>Ingen detaljer funnet for denne aktiviteten.</Text>;

    const chartData = details.map(d => ({
        time: new Date(d.timestamp).toLocaleTimeString(),
        "Puls": d.heart_rate,
        "Fart (km/t)": d.speed ? (d.speed * 3.6).toFixed(1) : null,
        "Høyde (moh)": d.altitude
    }));

    return (
        <main className="p-6 sm:p-10">
            <Title>Aktivitetsdetaljer for ID: {id}</Title>
            
            <Card className="mt-6">
                 <Title>Puls</Title>
                <AreaChart
                    className="h-72 mt-4"
                    data={chartData}
                    index="time"
                    categories={['Puls']}
                    colors={['red']}
                    yAxisWidth={40}
                />
            </Card>

            <Card className="mt-6">
                <Title>Fart</Title>
                <AreaChart
                    className="h-72 mt-4"
                    data={chartData}
                    index="time"
                    categories={['Fart (km/t)']}
                    colors={['blue']}
                    yAxisWidth={40}
                />
            </Card>

            <Card className="mt-6">
                <Title>Høyde</Title>
                <AreaChart
                    className="h-72 mt-4"
                    data={chartData}
                    index="time"
                    categories={['Høyde (moh)']}
                    colors={['green']}
                    yAxisWidth={40}
                />
            </Card>
        </main>
    );
};

export default ActivityDetailPage; 