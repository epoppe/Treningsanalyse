'use client';

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import styled from 'styled-components';
import { Activity } from '../store/slices/activitiesSlice';

const ChartContainer = styled.div`
  background: white;
  padding: 1rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 2rem;
  height: 400px;
`;

const Title = styled.h3`
  margin: 0 0 1rem 0;
  color: #2c3e50;
`;

interface ActivityChartProps {
  activities: Activity[];
  metric: 'distance' | 'duration' | 'average_hr' | 'calories';
  title: string;
}

export default function ActivityChart({ activities, metric, title }: ActivityChartProps) {
  // Sorter aktiviteter etter dato
  const sortedActivities = [...activities].sort(
    (a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
  );

  // Formater data for grafen
  const data = sortedActivities.map(activity => ({
    date: new Date(activity.start_time).toLocaleDateString('no-NO'),
    [metric]: activity[metric],
    name: activity.name
  }));

  // Bestem y-akse label basert på metrikk
  const getYAxisLabel = () => {
    switch (metric) {
      case 'distance':
        return 'Kilometer';
      case 'duration':
        return 'Minutter';
      case 'average_hr':
        return 'Puls (bpm)';
      case 'calories':
        return 'Kalorier';
      default:
        return '';
    }
  };

  return (
    <ChartContainer>
      <Title>{title}</Title>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            angle={-45}
            textAnchor="end"
            height={70}
            interval={0}
          />
          <YAxis
            label={{
              value: getYAxisLabel(),
              angle: -90,
              position: 'insideLeft'
            }}
          />
          <Tooltip
            content={({ active, payload, label }) => {
              if (active && payload && payload.length) {
                return (
                  <div style={{
                    background: 'white',
                    padding: '0.5rem',
                    border: '1px solid #ddd',
                    borderRadius: '4px'
                  }}>
                    <p><strong>{label}</strong></p>
                    <p>{payload[0].payload.name}</p>
                    <p>{`${payload[0].value} ${getYAxisLabel()}`}</p>
                  </div>
                );
              }
              return null;
            }}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey={metric}
            stroke="#3498db"
            strokeWidth={2}
            dot={{ r: 4 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
} 