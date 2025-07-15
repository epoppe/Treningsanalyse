'use client';

import {
  BarChart,
  Bar,
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

interface MonthlyComparisonChartProps {
  activities: Activity[];
  metric: 'distance' | 'time';
  title: string;
}

const monthNames = [
  'Jan', 'Feb', 'Mar', 'Apr', 'Mai', 'Jun',
  'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Des'
];

export default function MonthlyComparisonChart({ activities, metric, title }: MonthlyComparisonChartProps) {
  if (activities.length === 0) {
    return (
      <ChartContainer>
        <Title>{title}</Title>
        <p>Ingen data å vise for denne perioden.</p>
      </ChartContainer>
    );
  }

  // Vis data fra 2022 til inneværende år
  const currentYear = new Date().getFullYear();
  const years = [];
  for (let year = 2022; year <= currentYear; year++) {
    years.push(year);
  }
  
  // Grupper data per måned og år
  const monthlyData: { [key: string]: { [year: number]: number } } = {};
  
  // Initialiser alle måneder
  for (let month = 0; month < 12; month++) {
    const monthKey = monthNames[month];
    monthlyData[monthKey] = {};
    years.forEach(year => {
      monthlyData[monthKey][year] = 0;
    });
  }

  // Filtrer aktiviteter til 2022-2024
  const earliestDate = new Date(2022, 0, 1); // 1. januar 2022

  const relevantActivities = activities.filter(activity => {
    const activityDate = new Date(activity.startTimeLocal);
    return activityDate >= earliestDate;
  });

  // Grupper aktiviteter per måned og år
  relevantActivities.forEach(activity => {
    const date = new Date(activity.startTimeLocal);
    const year = date.getFullYear();
    const month = date.getMonth();
    const monthKey = monthNames[month];
    
    if (years.includes(year)) {
      let value = 0;
      if (metric === 'distance') {
        value = (activity.distance || 0) / 1000; // Konverter til km
      } else if (metric === 'time') {
        value = (activity.duration || 0) / 60; // Konverter til minutter
      }
      
      monthlyData[monthKey][year] += value;
    }
  });

  // Debug logging - kun grunnleggende info
  console.log(`[MonthlyComparisonChart] ${title}: ${activities.length} aktiviteter, ${relevantActivities.length} relevante aktiviteter (2022-${currentYear})`);

  // Konverter til format som Recharts kan bruke
  const chartData = monthNames.map(month => {
    const monthData: any = { month };
    years.forEach(year => {
      monthData[year.toString()] = monthlyData[month][year];
    });
    return monthData;
  });

  const getYAxisLabel = () => {
    switch (metric) {
      case 'distance':
        return 'Kilometer';
      case 'time':
        return 'Timer';
      default:
        return '';
    }
  };

  // Konverter tid til timer hvis nødvendig
  const finalChartData = chartData.map(data => {
    const newData = { ...data };
    if (metric === 'time') {
      years.forEach(year => {
        newData[year.toString()] = newData[year.toString()] / 60; // Konverter minutter til timer
      });
    }
    return newData;
  });

  // Farger for hvert år (dynamisk basert på antall år)
  const baseColors = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#8dd1e1', '#d084d0', '#82d982'];
  const yearColors = baseColors.slice(0, years.length);

  return (
    <ChartContainer>
      <Title>{title}</Title>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={finalChartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="month" />
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
                    {payload.map((entry, index) => (
                      <p key={index} style={{ color: entry.color }}>
                        {`${entry.dataKey}: ${entry.value?.toFixed(1)} ${getYAxisLabel().toLowerCase()}`}
                      </p>
                    ))}
                  </div>
                );
              }
              return null;
            }}
          />
          <Legend />
          {years.map((year, index) => (
            <Bar 
              key={year}
              dataKey={year.toString()}
              fill={yearColors[index]}
              name={year.toString()}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
} 