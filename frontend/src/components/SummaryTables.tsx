'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import styled from 'styled-components';

// Styled components
const Container = styled.div`
  margin: 2rem 0;
`;

const SectionTitle = styled.h2`
  color: #2c3e50;
  font-size: 1.5rem;
  margin-bottom: 1rem;
  text-align: center;
`;

const TabContainer = styled.div`
  display: flex;
  justify-content: center;
  margin-bottom: 2rem;
  border-bottom: 2px solid #ecf0f1;
`;

const Tab = styled.button<{ $active: boolean }>`
  padding: 1rem 2rem;
  background: ${props => props.$active ? '#3498db' : 'transparent'};
  color: ${props => props.$active ? 'white' : '#2c3e50'};
  border: none;
  border-bottom: 2px solid ${props => props.$active ? '#3498db' : 'transparent'};
  cursor: pointer;
  font-size: 1rem;
  font-weight: 500;
  transition: all 0.3s ease;

  &:hover {
    background: ${props => props.$active ? '#2980b9' : '#ecf0f1'};
  }
`;





const StatsInfo = styled.div`
  color: #666;
  font-size: 0.9rem;
`;

const TableContainer = styled.div`
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  overflow: hidden;
`;

const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
`;

const TableHeader = styled.th`
  background: #34495e;
  color: white;
  padding: 1rem;
  text-align: left;
  font-weight: 600;
  font-size: 0.9rem;
`;

const TableRow = styled.tr`
  &:nth-child(even) {
    background: #f8f9fa;
  }

  &:hover {
    background: #e8f4f8;
  }
`;

const TableCell = styled.td`
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #ecf0f1;
  font-size: 0.9rem;
`;

const LoadingSpinner = styled.div`
  border: 4px solid #f3f3f3;
  border-top: 4px solid #3498db;
  border-radius: 50%;
  width: 24px;
  height: 24px;
  animation: spin 1s linear infinite;
  margin: 2rem auto;

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
`;

const ErrorMessage = styled.div`
  color: #e74c3c;
  text-align: center;
  padding: 2rem;
  background: #fdf2f2;
  border-radius: 8px;
  margin: 1rem 0;
`;

const EmptyMessage = styled.div`
  color: #666;
  text-align: center;
  padding: 2rem;
  font-style: italic;
`;

// Types
interface DailySummary {
  date: string;
  total_activities: number;
  total_distance: number;
  total_duration: number;
  total_ascent: number;
  avg_heart_rate: number;
  avg_pace: number;
  total_calories: number;
}

interface WeeklySummary {
  week_start_date: string;
  week_end_date: string;
  total_activities: number;
  total_distance: number;
  total_duration: number;
  total_ascent: number;
  avg_heart_rate: number;
  avg_pace: number;
  total_calories: number;
  activities_per_day: number;
}

interface MonthlySummary {
  month_start_date: string;
  month_end_date: string;
  total_activities: number;
  total_distance: number;
  total_duration: number;
  total_ascent: number;
  avg_heart_rate: number;
  avg_pace: number;
  total_calories: number;
  activities_per_day: number;
  activities_per_week: number;
}

interface SummaryTablesProps {
  selectedActivityTypes?: string[];
}

type TabType = 'daily' | 'weekly' | 'monthly';

const SummaryTables: React.FC<SummaryTablesProps> = ({ selectedActivityTypes = [] }) => {

  
  const [activeTab, setActiveTab] = useState<TabType>('monthly');
  const [dailyData, setDailyData] = useState<DailySummary[]>([]);
  const [weeklyData, setWeeklyData] = useState<WeeklySummary[]>([]);
  const [monthlyData, setMonthlyData] = useState<MonthlySummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<any>(null);

  // Beregn startdato for siste 12 måneder
  const getStartDate = () => {
    const date = new Date();
    date.setMonth(date.getMonth() - 12);
    return date.toISOString().split('T')[0]; // Format: YYYY-MM-DD
  };

  // Stabiliser selectedActivityTypes for å unngå uendelige loops
  const stableSelectedTypes = useMemo(() => selectedActivityTypes, [selectedActivityTypes]);

  // Memoize buildQueryParams for å unngå unødvendige re-renders
  const memoizedBuildQueryParams = useMemo(() => {
    return (baseParams: string = '') => {
      const params = new URLSearchParams(baseParams);
      
      // Legg til startdato for siste 12 måneder
      params.append('start_date', getStartDate());
      
      // Legg til aktivitetstyper hvis spesifisert
      if (stableSelectedTypes.length > 0) {
        stableSelectedTypes.forEach(activityType => {
          params.append('activity_types', activityType);
        });
      }
      
      return params.toString();
    };
  }, [stableSelectedTypes]);

  // Fetch data functions
  const fetchDailyData = useCallback(async () => {
    try {
      const queryParams = memoizedBuildQueryParams('limit=30');
      const response = await fetch(`http://localhost:8000/api/analysis/daily-summaries?${queryParams}`);
      if (!response.ok) throw new Error('Failed to fetch daily summaries');
      const data = await response.json();
      setDailyData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'En ukjent feil oppstod');
    }
  }, [memoizedBuildQueryParams]);

  const fetchWeeklyData = useCallback(async () => {
    try {
      const queryParams = memoizedBuildQueryParams('limit=12');
      const response = await fetch(`http://localhost:8000/api/analysis/weekly-summaries?${queryParams}`);
      if (!response.ok) throw new Error('Failed to fetch weekly summaries');
      const data = await response.json();
      setWeeklyData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'En ukjent feil oppstod');
    }
  }, [memoizedBuildQueryParams]);

  const fetchMonthlyData = useCallback(async () => {
    try {
      const queryParams = memoizedBuildQueryParams('limit=12');
      const response = await fetch(`http://localhost:8000/api/analysis/monthly-summaries?${queryParams}`);
      if (!response.ok) throw new Error('Failed to fetch monthly summaries');
      const data = await response.json();
      setMonthlyData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'En ukjent feil oppstod');
    }
  }, [memoizedBuildQueryParams]);

  const fetchStats = useCallback(async () => {
    try {
      const response = await fetch('http://localhost:8000/api/analysis/summary-stats');
      if (!response.ok) throw new Error('Failed to fetch summary stats');
      const data = await response.json();
      setStats(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'En ukjent feil oppstod');
    }
  }, []);



  // Load data when component mounts or when selectedActivityTypes changes
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        await Promise.all([
          fetchDailyData(),
          fetchWeeklyData(),
          fetchMonthlyData(),
          fetchStats()
        ]);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'En ukjent feil oppstod');
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [fetchDailyData, fetchWeeklyData, fetchMonthlyData, fetchStats]); // Re-run when fetch functions change

  // Helper functions
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('nb-NO');
  };

  const formatDistance = (distance: number) => {
    return distance ? `${(distance / 1000).toFixed(1)} km` : '-';
  };

  const formatDuration = (seconds: number) => {
    if (!seconds) return '-';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return hours > 0 ? `${hours}t ${minutes}m` : `${minutes}m`;
  };

  const formatPace = (pace: number) => {
    if (pace == null || pace === 0) return '-';
    const minutes = Math.floor(pace / 60);
    const seconds = Math.floor(pace % 60);
    return `${minutes}:${seconds.toString().padStart(2, '0')} min/km`;
  };

  const formatHeartRate = (hr: number) => {
    return hr ? `${Math.round(hr)} bpm` : '-';
  };

  const formatCalories = (calories: number) => {
    return calories ? `${Math.round(calories)} kcal` : '-';
  };

  const formatElevation = (elevation: number) => {
    return elevation != null ? `${Math.round(elevation)} m` : '-';
  };

  // Render functions
  const renderDailyTable = () => (
    <TableContainer>
      <Table>
        <thead>
          <tr>
            <TableHeader>Dato</TableHeader>
            <TableHeader>Aktiviteter</TableHeader>
            <TableHeader>Distanse</TableHeader>
            <TableHeader>Tid</TableHeader>
            <TableHeader>Høydemeter</TableHeader>
            <TableHeader>Snitt puls</TableHeader>
            <TableHeader>Snitt tempo</TableHeader>
            <TableHeader>Kalorier</TableHeader>
          </tr>
        </thead>
        <tbody>
          {dailyData.map((day, index) => (
            <TableRow key={index}>
              <TableCell>{formatDate(day.date)}</TableCell>
              <TableCell>{day.total_activities}</TableCell>
              <TableCell>{formatDistance(day.total_distance)}</TableCell>
              <TableCell>{formatDuration(day.total_duration)}</TableCell>
              <TableCell>{formatElevation(day.total_ascent)}</TableCell>
              <TableCell>{formatHeartRate(day.avg_heart_rate)}</TableCell>
              <TableCell>{formatPace(day.avg_pace)}</TableCell>
              <TableCell>{formatCalories(day.total_calories)}</TableCell>
            </TableRow>
          ))}
        </tbody>
      </Table>
    </TableContainer>
  );

  const renderWeeklyTable = () => (
    <TableContainer>
      <Table>
        <thead>
          <tr>
            <TableHeader>Uke</TableHeader>
            <TableHeader>Aktiviteter</TableHeader>
            <TableHeader>Distanse</TableHeader>
            <TableHeader>Tid</TableHeader>
            <TableHeader>Høydemeter</TableHeader>
            <TableHeader>Snitt puls</TableHeader>
            <TableHeader>Snitt tempo</TableHeader>
            <TableHeader>Akt/dag</TableHeader>
            <TableHeader>Kalorier</TableHeader>
          </tr>
        </thead>
        <tbody>
          {weeklyData.map((week, index) => (
            <TableRow key={index}>
              <TableCell>
                {formatDate(week.week_start_date)} - {formatDate(week.week_end_date)}
              </TableCell>
              <TableCell>{week.total_activities}</TableCell>
              <TableCell>{formatDistance(week.total_distance)}</TableCell>
              <TableCell>{formatDuration(week.total_duration)}</TableCell>
              <TableCell>{formatElevation(week.total_ascent)}</TableCell>
              <TableCell>{formatHeartRate(week.avg_heart_rate)}</TableCell>
              <TableCell>{formatPace(week.avg_pace)}</TableCell>
              <TableCell>{week.activities_per_day?.toFixed(1) || '-'}</TableCell>
              <TableCell>{formatCalories(week.total_calories)}</TableCell>
            </TableRow>
          ))}
        </tbody>
      </Table>
    </TableContainer>
  );

  const renderMonthlyTable = () => (
    <TableContainer>
      <Table>
        <thead>
          <tr>
            <TableHeader>Måned</TableHeader>
            <TableHeader>Aktiviteter</TableHeader>
            <TableHeader>Distanse</TableHeader>
            <TableHeader>Tid</TableHeader>
            <TableHeader>Høydemeter</TableHeader>
            <TableHeader>Snitt puls</TableHeader>
            <TableHeader>Snitt tempo</TableHeader>
            <TableHeader>Akt/dag</TableHeader>
            <TableHeader>Akt/uke</TableHeader>
            <TableHeader>Kalorier</TableHeader>
          </tr>
        </thead>
        <tbody>
          {monthlyData.map((month, index) => (
            <TableRow key={index}>
              <TableCell>
                {formatDate(month.month_start_date)} - {formatDate(month.month_end_date)}
              </TableCell>
              <TableCell>{month.total_activities}</TableCell>
              <TableCell>{formatDistance(month.total_distance)}</TableCell>
              <TableCell>{formatDuration(month.total_duration)}</TableCell>
              <TableCell>{formatElevation(month.total_ascent)}</TableCell>
              <TableCell>{formatHeartRate(month.avg_heart_rate)}</TableCell>
              <TableCell>{formatPace(month.avg_pace)}</TableCell>
              <TableCell>{month.activities_per_day?.toFixed(1) || '-'}</TableCell>
              <TableCell>{month.activities_per_week?.toFixed(1) || '-'}</TableCell>
              <TableCell>{formatCalories(month.total_calories)}</TableCell>
            </TableRow>
          ))}
        </tbody>
      </Table>
    </TableContainer>
  );

  const getCurrentData = () => {
    switch (activeTab) {
      case 'daily':
        return dailyData;
      case 'weekly':
        return weeklyData;
      case 'monthly':
        return monthlyData;
      default:
        return [];
    }
  };

  const getCurrentTable = () => {
    switch (activeTab) {
      case 'daily':
        return renderDailyTable();
      case 'weekly':
        return renderWeeklyTable();
      case 'monthly':
        return renderMonthlyTable();
      default:
        return null;
    }
  };

  return (
    <Container>
      <SectionTitle>Detaljert statistikk - Siste 12 måneder</SectionTitle>
      
      {/* Filter indikator */}
      {selectedActivityTypes.length > 0 && (
        <div style={{ 
          marginBottom: '1rem', 
          padding: '0.5rem', 
          backgroundColor: '#e8f4f8', 
          border: '1px solid #3498db',
          borderRadius: '4px',
          fontSize: '0.9rem',
          color: '#2c3e50',
          textAlign: 'center'
        }}>
          <strong>Filtrert for aktivitetstyper:</strong> {selectedActivityTypes.join(', ')}
        </div>
      )}
      
      <TabContainer>
        <Tab 
          $active={activeTab === 'daily'} 
          onClick={() => setActiveTab('daily')}
        >
          Daglige sammendrag
        </Tab>
        <Tab 
          $active={activeTab === 'weekly'} 
          onClick={() => setActiveTab('weekly')}
        >
          Ukentlige sammendrag
        </Tab>
        <Tab 
          $active={activeTab === 'monthly'} 
          onClick={() => setActiveTab('monthly')}
        >
          Månedlige sammendrag
        </Tab>
      </TabContainer>

             {stats && (
         <StatsInfo>
           Totalt: {stats.daily?.count || 0} dager, {stats.weekly?.count || 0} uker, {stats.monthly?.count || 0} måneder
         </StatsInfo>
       )}

      {error && <ErrorMessage>{error}</ErrorMessage>}

      {loading ? (
        <LoadingSpinner />
      ) : getCurrentData().length === 0 ? (
        <EmptyMessage>
          Ingen data tilgjengelig.
        </EmptyMessage>
      ) : (
        getCurrentTable()
      )}
    </Container>
  );
};

export default SummaryTables; 