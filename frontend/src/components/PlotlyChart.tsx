"use client";

import { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { Text } from '@tremor/react';

const Plot = dynamic(() => import('react-plotly.js'), {
    ssr: false,
});

interface PlotlyChartProps {
    data: any[];
    xKey: string;
    yKeys: string[];
    title: string;
    yAxisTitle: string;
}

const PlotlyChart = ({ data, xKey, yKeys, title, yAxisTitle }: PlotlyChartProps) => {
    if (!data || data.length === 0) {
        return <Text>Ingen data tilgjengelig for å vise grafen.</Text>;
    }

    const traces = yKeys.map(yKey => ({
        x: data.map(item => item[xKey]),
        y: data.map(item => item[yKey]),
        name: yKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()), // Prettify name
        type: 'scatter',
        mode: 'lines+markers',
    }));

    const layout = {
        title: title,
        xaxis: {
            title: 'Dato',
        },
        yaxis: {
            title: yAxisTitle,
        },
        autosize: true,
        margin: { l: 50, r: 50, b: 50, t: 50, pad: 4 },
    };

    return (
        <Plot
            data={traces}
            layout={layout}
            style={{ width: '100%', height: '100%' }}
            useResizeHandler={true}
        />
    );
};

export default PlotlyChart; 