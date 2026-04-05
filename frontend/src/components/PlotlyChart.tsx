"use client";

import { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { Text } from '@tremor/react';

const Plot = dynamic<any>(() => import('react-plotly.js'), {
    ssr: false,
});

interface PlotlyChartProps {
    data: any[];
    xKey: string;
    yKeys: string[];
    title: string;
    yAxisTitle: string;
    /** Standard «Dato» for tidsserier; sett eksplisitt for f.eks. scatter mot andre X-verdier */
    xAxisTitle?: string;
    traceMode?: 'lines+markers' | 'markers' | 'lines';
    /** Nøkkel per datapunkt for hover (f.eks. aktivitetsnavn + dato) */
    textKey?: string;
}

const PlotlyChart = ({
    data,
    xKey,
    yKeys,
    title,
    yAxisTitle,
    xAxisTitle = 'Dato',
    traceMode = 'lines+markers',
    textKey,
}: PlotlyChartProps) => {
    if (!data || data.length === 0) {
        return <Text>Ingen data tilgjengelig for å vise grafen.</Text>;
    }

    const hoverTemplate = textKey
        ? `%{text}<br>${xAxisTitle}: %{x}<br>${yAxisTitle}: %{y}<extra></extra>`
        : undefined;

    const traces = yKeys.map(yKey => ({
        x: data.map(item => item[xKey]),
        y: data.map(item => item[yKey]),
        name: yKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()), // Prettify name
        type: 'scatter',
        mode: traceMode,
        ...(textKey
            ? { text: data.map(item => String(item[textKey] ?? '')), hovertemplate: hoverTemplate }
            : {}),
    }));

    const layout = {
        title: title,
        xaxis: {
            title: xAxisTitle,
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