"use client";

import { useState, useEffect } from 'react';
import Plot from 'react-plotly.js';
import { Text } from '@tremor/react';

interface PlotlyChartProps {
    activityId: number;
    chartType: 'pulse' | 'altitude' | 'pace'; // Add more types as needed
}

const PlotlyChart = ({ activityId, chartType }: PlotlyChartProps) => {
    const [figure, setFigure] = useState(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchChartData = async () => {
            setIsLoading(true);
            setError(null);
            try {
                const res = await fetch(`/api/activities/${activityId}/charts/${chartType}`);
                if (!res.ok) {
                    const errorText = await res.text();
                    throw new Error(`Feil ved lasting av graf: ${errorText || res.statusText}`);
                }
                const data = await res.json();
                setFigure(data);
            } catch (err: any) {
                // Prøver å parse feilmeldingen som JSON for å få en penere feilmelding
                try {
                    const errorJson = JSON.parse(err.message.substring(err.message.indexOf('{')));
                    setError(errorJson.detail || err.message);
                } catch {
                    setError(err.message);
                }
            } finally {
                setIsLoading(false);
            }
        };

        fetchChartData();
    }, [activityId, chartType]);

    if (isLoading) return <Text>Laster inn graf...</Text>;
    if (error) return <Text>Feil ved lasting av graf: {error}</Text>;
    if (!figure) return <Text>Ingen grafdata funnet.</Text>;

    return (
        <Plot
            data={figure.data}
            layout={figure.layout}
            style={{ width: '100%', height: '100%' }}
            useResizeHandler={true}
        />
    );
};

export default PlotlyChart; 