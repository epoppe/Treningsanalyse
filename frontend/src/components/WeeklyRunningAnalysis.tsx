'use client';

import React, { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import styled from 'styled-components';
import { Activity } from '../store/slices/activitiesSlice';
import { getISOWeek, startOfISOWeek, format, differenceInDays, startOfMonth } from 'date-fns';

const NoDataMessage = styled.div`
  background-color: #fff3cd;
  color: #856404;
  padding: 1rem;
  border: 1px solid #ffeeba;
  border-radius: 0.25rem;
  text-align: center;
  font-weight: bold;
`;

const AnalysisContainer = styled.div`
  display: grid;
  grid-template-columns: 1fr;
  gap: 2rem;
  margin-top: 2rem;
`;

const ChartWrapper = styled.div`
  background: white;
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  height: 400px;
`;

const ChartTitle = styled.h3`
  margin: 0 0 1rem 0;
  color: #2c3e50;
  text-align: center;
`;

const ChartHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 0 20px;

  label {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
  }
`;

interface WeeklyRunningAnalysisProps {
  activities: Activity[];
}

const calculateLinearRegression = (data: { x: number; y: number }[]) => {
  const n = data.length;
  if (n < 2) {
    return { slope: 0, intercept: 0 };
  }

  const sum = data.reduce((acc, point) => {
    acc.x += point.x;
    acc.y += point.y;
    acc.xy += point.x * point.y;
    acc.x2 += point.x * point.x;
    return acc;
  }, { x: 0, y: 0, xy: 0, x2: 0 });

  const slope = (n * sum.xy - sum.x * sum.y) / (n * sum.x2 - sum.x * sum.x);
  const intercept = (sum.y - slope * sum.x) / n;

  return { slope, intercept };
};

const WeeklyRunningAnalysis = ({ activities }: WeeklyRunningAnalysisProps) => {
  const [showTrend, setShowTrend] = useState(false);
  
  if (!Array.isArray(activities)) {
    return <AnalysisContainer>Venter på aktivitetsdata...</AnalysisContainer>;
  }

  const runningActivities = activities.filter(
    a => a.type?.toLowerCase().includes('running') && a.type?.toLowerCase() !== 'treadmill_running'
  );

  if (runningActivities.length === 0) {
    return <AnalysisContainer>Ingen løpedata tilgjengelig for analyse.</AnalysisContainer>;
  }

  const activityDataList = runningActivities
    .map(activity => {
      const avgHR = activity.averageHR && activity.averageHR > 0 ? activity.averageHR : null;
      const avgSpeed = activity.averageSpeed && activity.averageSpeed > 0 ? activity.averageSpeed : null;
      let runningEconomy = null;

      if (avgHR && avgSpeed) {
        const avgSpeedKmh = avgSpeed * 3.6;
        runningEconomy = (avgSpeedKmh / avgHR) * 100;
      }

      return {
        date: new Date(activity.start_time),
        avgHR,
        avgSpeed,
        runningEconomy,
      };
    })
    .filter(item => item.runningEconomy !== null)
    .sort((a, b) => a.date.getTime() - b.date.getTime());

  // Determine aggregation period
  const firstDate = activityDataList[0].date;
  const lastDate = activityDataList[activityDataList.length - 1].date;
  const isLongTerm = differenceInDays(lastDate, firstDate) > 365;
  const aggregationPeriod = isLongTerm ? 'monthly' : 'weekly';
  
  const aggregatedData = activityDataList.reduce((acc, activity) => {
    const weekKey = aggregationPeriod === 'weekly' 
      ? format(startOfISOWeek(activity.date), 'yyyy-MM-dd')
      : format(startOfMonth(activity.date), 'yyyy-MM-dd');

    if (!acc[weekKey]) {
      acc[weekKey] = {
        date: weekKey,
        totalHR: 0,
        hrCount: 0,
        totalSpeed: 0,
        speedCount: 0,
        totalRunningEconomy: 0,
        runningEconomyCount: 0,
      };
    }
    
    if (activity.avgHR) {
      acc[weekKey].totalHR += activity.avgHR;
      acc[weekKey].hrCount += 1;
    }
    if (activity.avgSpeed) {
      acc[weekKey].totalSpeed += activity.avgSpeed;
      acc[weekKey].speedCount += 1;
    }
    if (activity.runningEconomy) {
        acc[weekKey].totalRunningEconomy += activity.runningEconomy;
        acc[weekKey].runningEconomyCount += 1;
    }
    
    return acc;
  }, {} as Record<string, any>);

  const chartData = Object.values(aggregatedData)
    .map(period => ({
      date: period.date,
      avgHR: period.hrCount > 0 ? period.totalHR / period.hrCount : null,
      avgSpeed: period.speedCount > 0 ? (period.totalSpeed / period.speedCount) * 3.6 : null, // m/s to km/h
      avgRunningEconomy: period.runningEconomyCount > 0 ? period.totalRunningEconomy / period.runningEconomyCount : null,
    }))
    .filter(period => period.avgHR !== null || period.avgSpeed !== null || period.avgRunningEconomy !== null)
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

  // Calculate Trend Line for Running Economy
  const economyDataPoints = chartData
    .map(d => ({
      x: new Date(d.date).getTime(),
      y: d.avgRunningEconomy,
    }))
    .filter(d => d.y !== null);

  const { slope, intercept } = calculateLinearRegression(economyDataPoints);

  const dataWithTrend = chartData.map(d => {
    const trendValue = slope * new Date(d.date).getTime() + intercept;
    return {
      ...d,
      trend: trendValue,
    };
  });

  if (chartData.length === 0) {
    return <AnalysisContainer>Ingen data å vise i grafene.</AnalysisContainer>;
  }

  const chartTitle = aggregationPeriod === 'weekly' ? 'Ukentlig' : 'Månedlig';
  const dateFormat = aggregationPeriod === 'weekly' ? 'dd/MM' : 'MMM yy';

  return (
    <AnalysisContainer>
      <ChartWrapper>
        <ChartHeader>
          <ChartTitle>{chartTitle} Løpsøkonomi</ChartTitle>
          <label>
            <input type="checkbox" checked={showTrend} onChange={() => setShowTrend(!showTrend)} />
            Vis trendlinje
          </label>
        </ChartHeader>
        <ResponsiveContainer width="100%" height="90%">
          <LineChart data={dataWithTrend}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tickFormatter={(d) => format(new Date(d), dateFormat)} />
            <YAxis 
              domain={[4.66, 8.66]} 
              tickFormatter={(tick) => typeof tick === 'number' ? tick.toFixed(2) : tick}
            />
            <Tooltip 
              formatter={(value: number, name: string) => {
                if (name === 'Løpsøkonomi' || name === 'Trend') {
                  return [value.toFixed(2), name];
                }
                return [value, name];
              }}
            />
            <Legend />
            <Line type="monotone" dataKey="avgRunningEconomy" name="Løpsøkonomi" stroke="#8e44ad" dot={false} />
            {showTrend && (
              <Line 
                type="monotone" 
                dataKey="trend" 
                name="Trend" 
                stroke="#ff7300" 
                strokeDasharray="5 5" 
                dot={false} 
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </ChartWrapper>

      <ChartWrapper>
        <ChartTitle>{chartTitle} Gjennomsnittspuls</ChartTitle>
        <ResponsiveContainer width="100%" height="90%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tickFormatter={(d) => format(new Date(d), dateFormat)} />
            <YAxis domain={['dataMin - 10', 'dataMax + 5']} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="avgHR" name="Snittpuls (slag/min)" stroke="#c0392b" />
          </LineChart>
        </ResponsiveContainer>
      </ChartWrapper>

      <ChartWrapper>
        <ChartTitle>{chartTitle} Gjennomsnittsfart</ChartTitle>
        <ResponsiveContainer width="100%" height="90%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tickFormatter={(d) => format(new Date(d), dateFormat)} />
            <YAxis domain={['dataMin - 1', 'dataMax + 1']} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="avgSpeed" name="Snittfart (km/t)" stroke="#2980b9" />
          </LineChart>
        </ResponsiveContainer>
      </ChartWrapper>
    </AnalysisContainer>
  );
};

export default WeeklyRunningAnalysis; 