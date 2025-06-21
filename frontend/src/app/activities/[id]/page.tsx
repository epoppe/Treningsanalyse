"use client";

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Card, Title, AreaChart, Text } from '@tremor/react';

interface Activity {
    id: number;
    name: string;
    type: string;
    // Legg til andre felter fra aktivitetsobjektet ved behov
}

interface ActivityDetail {
    timestamp: string;
    latitude?: number;
    longitude?: number;
    altitude?: number;
    speed?: number;
    heart_rate?: number;
    cadence?: number;
}

// Hjelpefunksjon for å formatere tempo
const formatPace = (pace: number): string => {
    if (isNaN(pace) || !isFinite(pace)) {
        return "0:00";
    }
    const minutes = Math.floor(pace);
    const seconds = Math.round((pace - minutes) * 60);
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
};


const ActivityDetailPage = () => {
    const params = useParams();
    const { id } = params;
    
    const [activity, setActivity] = useState<Activity | null>(null);
    const [details, setDetails] = useState<ActivityDetail[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (id) {
            const fetchActivityData = async () => {
                try {
                    setLoading(true);
                    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
                    
                    // Hent både aktivitetsinfo og detaljer
                    const [activityResponse, detailsResponse] = await Promise.all([
                        fetch(`${baseUrl}/api/activities`), // Antar dette endepunktet kan filtrere på id, eller at vi finner aktiviteten i listen
                        fetch(`${baseUrl}/api/activities/${id}/details`)
                    ]);

                    if (!activityResponse.ok || !detailsResponse.ok) {
                        throw new Error(`Klarte ikke å hente data`);
                    }
                    
                    const activitiesData = await activityResponse.json();
                    const detailsData = await detailsResponse.json();
                    
                    const currentActivity = activitiesData.activities.find((a: Activity) => a.id === parseInt(id as string, 10));

                    setActivity(currentActivity);
                    setDetails(detailsData);

                } catch (e: any) {
                    setError(e.message);
                } finally {
                    setLoading(false);
                }
            };
            fetchActivityData();
        }
    }, [id]);

    if (loading) return <Text>Laster aktivitetsdetaljer...</Text>;
    if (error) return <Text>Feil: {error}</Text>;
    if (!details.length || !activity) return <Text>Ingen detaljer funnet for denne aktiviteten.</Text>;
    
    const isRunning = activity.type.toLowerCase().includes('running');
    
    // Først, transformer dataene og finn maks-verdi hvis det er løping
    const processedDetails = details.map(d => {
        // ANTAR NÅ AT d.speed ER I KM/T, ikke m/s.
        const paceMinPerKm = d.speed && d.speed > 0.5 ? 60 / d.speed : 0; // 60 min / (km/t) -> min/km
        return {
            ...d,
            pace: paceMinPerKm
        };
    });

    const maxPace = isRunning ? Math.max(...processedDetails.map(d => d.pace).filter(p => p > 0 && isFinite(p))) : 0;

    const speedOrPaceCategory = isRunning ? 'Tempo (min/km)' : 'Fart (km/t)';

    const chartData = processedDetails.map(d => {
        const speedKmh = d.speed ? d.speed : 0; // The speed is already in km/h
        
        let invertedPace = null;
        if (isRunning && d.pace > 0 && isFinite(d.pace)) {
            // Vi inverterer slik at lavest verdi (raskest) blir høyest i grafen
            invertedPace = maxPace - d.pace;
        }

        return {
            time: new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            'Puls (slag/min)': d.heart_rate ?? null,
            [speedOrPaceCategory]: isRunning ? invertedPace : speedKmh,
            'Høydemeter (moh)': d.altitude ?? null,
            originalPace: d.pace
        };
    });
    
    // Formatter for y-aksen for tempo, som nå må regne tilbake den inverterte verdien
    const paceValueFormatter = (value: number) => {
        if (!isRunning || !isFinite(maxPace) || maxPace === 0) return "N/A";
        // Regn tilbake til den faktiske pace-verdien
        const actualPace = maxPace - value;
        return formatPace(actualPace);
    };

    return (
        <main className="p-6 sm:p-10">
            <Title>{activity.name} ({id})</Title>
            
            <Card className="mt-6">
                <Title>Puls</Title>
                <AreaChart
                    className="h-72 mt-4"
                    data={chartData}
                    index="time"
                    categories={['Puls (slag/min)']}
                    colors={['red']}
                    yAxisWidth={60}
                />
            </Card>

            <Card className="mt-6">
                <Title>{speedOrPaceCategory}</Title>
                <AreaChart
                    className="h-72 mt-4"
                    data={chartData}
                    index="time"
                    categories={[speedOrPaceCategory]}
                    colors={['blue']}
                    yAxisWidth={60}
                    valueFormatter={isRunning ? paceValueFormatter : undefined}
                />
            </Card>

            <Card className="mt-6">
                <Title>Høydemeter</Title>
                <AreaChart
                    className="h-72 mt-4"
                    data={chartData}
                    index="time"
                    categories={['Høydemeter (moh)']}
                    colors={['green']}
                    yAxisWidth={60}
                />
            </Card>
        </main>
    );
};

export default ActivityDetailPage; 