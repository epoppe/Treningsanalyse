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

  // Beregn de siste 4 årene
  const currentYear = new Date().getFullYear();
  const years = [currentYear - 3, currentYear - 2, currentYear - 1, currentYear];
  
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

  // Filtrer aktiviteter til siste 4 år - bruk den eldste året i years array
  const earliestYear = Math.min(...years);
  const earliestDate = new Date(earliestYear, 0, 1); // 1. januar av det eldste året

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
  console.log(`[MonthlyComparisonChart] ${title}: ${activities.length} aktiviteter, ${relevantActivities.length} relevante aktiviteter (${earliestDate.getFullYear()}-${new Date().getFullYear()})`);

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

  // Farger for hvert år
  const yearColors = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300'];

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