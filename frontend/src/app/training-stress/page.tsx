'use client';

import React, { useState, useEffect } from 'react';
import styled from 'styled-components';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title as ChartTitle,
  Tooltip,
  Legend,
  Filler
} from 'chart.js';
import { Line } from 'react-chartjs-2';

// Registrer Chart.js komponenter
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ChartTitle,
  Tooltip,
  Legend,
  Filler
);

// Styled components
const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 1rem;
`;

const Title = styled.h1`
  color: #2c3e50;
  text-align: center;
  margin-bottom: 1rem;
  font-size: 2rem;
`;

const DateRangeSelector = styled.div`
  display: flex;
  justify-content: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
  align-items: center;
  flex-wrap: wrap;
`;

const DateInput = styled.input`
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 1rem;
`;

const Button = styled.button`
  padding: 0.5rem 1rem;
  background: #3498db;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
  transition: background 0.3s ease;

  &:hover {
    background: #2980b9;
  }

  &:disabled {
    background: #bdc3c7;
    cursor: not-allowed;
  }
`;

const MetricsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
`;

const MetricCard = styled.div`
  background: white;
  border-radius: 8px;
  padding: 0.75rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  border-left: 4px solid #3498db;
`;

const MetricTitle = styled.h3`
  color: #2c3e50;
  margin-bottom: 0.25rem;
  font-size: 0.8rem;
  font-weight: 600;
`;

const MetricValue = styled.div`
  font-size: 1.3rem;
  font-weight: bold;
  color: #3498db;
  margin-bottom: 0.125rem;
`;

const MetricLabel = styled.div`
  color: #666;
  font-size: 0.7rem;
`;

const ChartContainer = styled.div`
  background: white;
  border-radius: 8px;
  padding: 0.75rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 1.5rem;
`;

const ChartWrapper = styled.div`
  position: relative;
  height: 450px;
  width: 100%;
  margin-top: 0.5rem;
`;

const ChartTitleStyled = styled.h3`
  color: #2c3e50;
  margin-bottom: 0.25rem;
  font-size: 1rem;
  text-align: center;
`;

const LoadingSpinner = styled.div`
  border: 4px solid #f3f3f3;
  border-top: 4px solid #3498db;
  border-radius: 50%;
  width: 40px;
  height: 40px;
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

const ActivityList = styled.div`
  background: white;
  border-radius: 8px;
  padding: 1rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 1.5rem;
`;

const ActivityItem = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem;
  border-bottom: 1px solid #ecf0f1;
  
  &:last-child {
    border-bottom: none;
  }
  
  &:hover {
    background: #f8f9fa;
  }
`;

const ActivityInfo = styled.div`
  flex: 1;
`;

const ActivityName = styled.div`
  font-weight: bold;
  color: #2c3e50;
  margin-bottom: 0.25rem;
`;

const ActivityDetails = styled.div`
  color: #666;
  font-size: 0.9rem;
`;

const TSSValue = styled.div<{ tss: number }>`
  font-weight: bold;
  color: ${props => {
    // EPOC-baserte verdier: 50-400 er typisk for løping
    if (props.tss >= 300) return '#8b0000'; // Mørk rød for svært høy TSS
    if (props.tss >= 200) return '#e74c3c'; // Rød for høy TSS
    if (props.tss >= 100) return '#f39c12'; // Oransje for moderat TSS
    if (props.tss >= 50) return '#27ae60'; // Grønn for lav TSS
    return '#95a5a6'; // Grå for svært lav TSS
  }};
  font-size: 1rem;
`;

const FormIndicator = styled.div<{ form: number }>`
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  font-weight: bold;
  color: white;
  font-size: 0.8rem;
  background: ${props => {
    if (props.form >= 10) return '#27ae60'; // Grønn - god form
    if (props.form >= 0) return '#f39c12'; // Oransje - nøytral
    return '#e74c3c'; // Rød - tretthet
  }};
`;

// Types
interface DailyData {
  date: string;
  tss: number;
  ctl: number;
  atl: number;
  form: number;
}

interface Summary {
  current_ctl: number;
  current_atl: number;
  current_form: number;
  total_tss_period: number;
  avg_daily_tss: number;
  max_daily_tss: number;
  days_with_activity: number;
  total_days: number;
}

interface Activity {
  activity_id: string;
  activity_name: string;
  date: string;
  duration: number;
  distance: number;
  tss: number;  // Dette er nå EPOC-verdien
  training_effect?: number;
  anaerobic_training_effect?: number;
  average_heart_rate?: number;
}

interface TrainingStressData {
  daily_data: DailyData[];
  summary: Summary;
  activities: Activity[];
}

const TrainingStressPage: React.FC = () => {
  const [startDate, setStartDate] = useState<string>(
    new Date(Date.now() - 180 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
  );
  const [endDate, setEndDate] = useState<string>(
    new Date().toISOString().split('T')[0]
  );
  const [data, setData] = useState<TrainingStressData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTrainingStressData = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(
        `/api/training-stress/metrics?start_date=${startDate}&end_date=${endDate}`
      );
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const result = await response.json();
      
      if (result.data) {
        setData(result.data);
      } else {
        setError(result.message || 'Ingen data tilgjengelig');
      }
      
    } catch (err: any) {
      setError(err.message || 'En feil oppstod ved henting av data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrainingStressData();
  }, [startDate, endDate]);

  const handleDateChange = (field: 'start' | 'end') => (event: React.ChangeEvent<HTMLInputElement>) => {
    if (field === 'start') {
      setStartDate(event.target.value);
    } else {
      setEndDate(event.target.value);
    }
  };

  const getFormStatus = (form: number) => {
    if (form >= 10) return 'God form';
    if (form >= 0) return 'Nøytral';
    return 'Tretthet';
  };

  const getTSSStatus = (tss: number) => {
    // EPOC-baserte verdier: 50-400 er typisk for løping
    if (tss >= 300) return 'Svært høy belastning';
    if (tss >= 200) return 'Høy belastning';
    if (tss >= 100) return 'Moderat belastning';
    if (tss >= 50) return 'Lav belastning';
    return 'Svært lav belastning';
  };

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return hours > 0 ? `${hours}t ${minutes}m` : `${minutes}m`;
  };

  const formatDistance = (distance: number) => {
    return `${(distance / 1000).toFixed(1)} km`;
  };

  const formatDateForChart = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('nb-NO', { month: 'short', day: 'numeric' });
  };

  const getFormColor = (formValue: number) => {
    if (formValue >= 10) return '#27ae60'; // Grønn - god form
    if (formValue >= 0) return '#f39c12'; // Oransje - nøytral
    return '#e74c3c'; // Rød - tretthet
  };

  return (
    <Container>
      <Title>📊 Training Stress Score (EPOC-basert)</Title>
      
      <DateRangeSelector>
        <label htmlFor="start-date">Fra:</label>
        <DateInput
          id="start-date"
          type="date"
          value={startDate}
          onChange={handleDateChange('start')}
          max={endDate}
        />
        <label htmlFor="end-date">Til:</label>
        <DateInput
          id="end-date"
          type="date"
          value={endDate}
          onChange={handleDateChange('end')}
          max={new Date().toISOString().split('T')[0]}
        />
        <Button onClick={fetchTrainingStressData} disabled={loading}>
          {loading ? 'Henter...' : 'Oppdater'}
        </Button>
      </DateRangeSelector>

      {error && <ErrorMessage>{error}</ErrorMessage>}

      {loading ? (
        <LoadingSpinner />
      ) : data ? (
        <>
          <MetricsGrid>
            <MetricCard>
              <MetricTitle>CTL (Chronic Training Load)</MetricTitle>
              <MetricValue style={{ color: '#3498db' }}>
                {data.summary.current_ctl}
              </MetricValue>
              <MetricLabel>42-dagers eksponentiell glidende gjennomsnitt</MetricLabel>
            </MetricCard>

            <MetricCard>
              <MetricTitle>ATL (Acute Training Load)</MetricTitle>
              <MetricValue style={{ color: '#e67e22' }}>
                {data.summary.current_atl}
              </MetricValue>
              <MetricLabel>7-dagers eksponentiell glidende gjennomsnitt</MetricLabel>
            </MetricCard>

            <MetricCard>
              <MetricTitle>Form (Fitness/Fatigue)</MetricTitle>
              <FormIndicator form={data.summary.current_form}>
                {data.summary.current_form}
              </FormIndicator>
              <MetricLabel>{getFormStatus(data.summary.current_form)}</MetricLabel>
            </MetricCard>

            <MetricCard>
              <MetricTitle>Total EPOC/TSS (Periode)</MetricTitle>
              <MetricValue style={{ color: '#9b59b6' }}>
                {data.summary.total_tss_period}
              </MetricValue>
              <MetricLabel>Kumulativ EPOC (brukes som TSS)</MetricLabel>
            </MetricCard>

            <MetricCard>
              <MetricTitle>Gjennomsnittlig Daglig EPOC/TSS</MetricTitle>
              <MetricValue style={{ color: '#f39c12' }}>
                {data.summary.avg_daily_tss}
              </MetricValue>
              <MetricLabel>Per dag i perioden</MetricLabel>
            </MetricCard>

            <MetricCard>
              <MetricTitle>Høyeste Daglig TSS</MetricTitle>
              <MetricValue style={{ color: '#e74c3c' }}>
                {data.summary.max_daily_tss}
              </MetricValue>
              <MetricLabel>Maksimal daglig belastning</MetricLabel>
            </MetricCard>

            <MetricCard>
              <MetricTitle>Aktivitetsdager</MetricTitle>
              <MetricValue style={{ color: '#27ae60' }}>
                {data.summary.days_with_activity} / {data.summary.total_days}
              </MetricValue>
              <MetricLabel>Dager med aktivitet i perioden</MetricLabel>
            </MetricCard>
          </MetricsGrid>

          <ChartContainer>
            <ChartTitleStyled>Training Load Over Tid</ChartTitleStyled>
            <ChartWrapper>
              <Line
                data={{
                  labels: data.daily_data.map(day => formatDateForChart(day.date)),
                  datasets: [
                    {
                      label: 'CTL',
                      data: data.daily_data.map(day => day.ctl),
                      borderColor: '#3498db',
                      backgroundColor: 'rgba(52, 152, 219, 0.2)',
                      fill: true,
                      tension: 0.4,
                    },
                    {
                      label: 'ATL',
                      data: data.daily_data.map(day => day.atl),
                      borderColor: '#e67e22',
                      backgroundColor: 'rgba(230, 126, 34, 0.2)',
                      fill: true,
                      tension: 0.4,
                    },
                    {
                      label: 'TSS',
                      data: data.daily_data.map(day => day.tss),
                      borderColor: '#9b59b6',
                      backgroundColor: 'rgba(155, 89, 182, 0.2)',
                      fill: false,
                      tension: 0,
                      pointRadius: 4,
                      pointHoverRadius: 6,
                      pointBackgroundColor: '#9b59b6',
                      pointBorderColor: '#9b59b6',
                      borderWidth: 0,
                    },
                  ],
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    legend: {
                      position: 'top',
                    },
                    tooltip: {
                      callbacks: {
                        label: function(context) {
                          let label = context.dataset.label || '';
                          if (label) {
                            label += ': ';
                          }
                          if (context.parsed.y !== null) {
                            label += context.parsed.y.toFixed(1);
                          }
                          return label;
                        }
                      }
                    }
                  },
                  scales: {
                    x: {
                      type: 'category',
                      grid: {
                        display: false,
                      },
                      ticks: {
                        color: '#666',
                        maxRotation: 45,
                      },
                    },
                    y: {
                      beginAtZero: true,
                      grid: {
                        color: '#ecf0f1',
                      },
                      ticks: {
                        color: '#666',
                      },
                      title: {
                        display: true,
                        text: 'TSS',
                        color: '#666',
                        font: {
                          size: 14,
                        },
                      },
                    },
                  },
                }}
              />
            </ChartWrapper>
          </ChartContainer>

          <ChartContainer>
            <ChartTitleStyled>Form (Fitness/Fatigue) Over Tid</ChartTitleStyled>
            <ChartWrapper>
              <Line
                data={{
                  labels: data.daily_data.map(day => formatDateForChart(day.date)),
                  datasets: [
                    {
                      label: 'Form',
                      data: data.daily_data.map(day => day.form),
                      borderColor: '#27ae60',
                      backgroundColor: 'rgba(39, 174, 96, 0.2)',
                      fill: true,
                      tension: 0.4,
                      pointRadius: 4,
                      pointHoverRadius: 6,
                    },
                    {
                      label: 'Nøytral (0)',
                      data: data.daily_data.map(() => 0),
                      borderColor: '#bdc3c7',
                      backgroundColor: 'transparent',
                      borderDash: [5, 5],
                      fill: false,
                      pointRadius: 0,
                      pointHoverRadius: 0,
                    },
                  ],
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    legend: {
                      position: 'top',
                    },
                    tooltip: {
                      callbacks: {
                        label: function(context) {
                          if (context.dataset.label === 'Form') {
                            const value = context.parsed.y;
                            let status = '';
                            if (value >= 10) status = ' (God form)';
                            else if (value >= 0) status = ' (Nøytral)';
                            else status = ' (Tretthet)';
                            return `Form: ${value.toFixed(1)}${status}`;
                          }
                          return context.dataset.label || '';
                        }
                      }
                    },
                  },
                  scales: {
                    x: {
                      type: 'category',
                      grid: {
                        display: false,
                      },
                      ticks: {
                        color: '#666',
                        maxRotation: 45,
                      },
                    },
                    y: {
                      grid: {
                        color: '#ecf0f1',
                      },
                      ticks: {
                        color: '#666',
                        callback: function(value) {
                          if (value >= 10) return `${value} (God form)`;
                          if (value >= 0) return `${value} (Nøytral)`;
                          return `${value} (Tretthet)`;
                        }
                      },
                      title: {
                        display: true,
                        text: 'Form Score',
                        color: '#666',
                        font: {
                          size: 14,
                        },
                      },
                    },
                  },
                }}
              />
            </ChartWrapper>
          </ChartContainer>

          <ActivityList>
            <MetricTitle>Aktiviteter med EPOC/TSS</MetricTitle>
            {data.activities.length > 0 ? (
              data.activities.map((activity) => (
                <ActivityItem key={activity.activity_id}>
                  <ActivityInfo>
                    <ActivityName>{activity.activity_name}</ActivityName>
                    <ActivityDetails>
                      {new Date(activity.date).toLocaleDateString('nb-NO')} • 
                      {formatDistance(activity.distance)} • 
                      {formatDuration(activity.duration)}
                    </ActivityDetails>
                  </ActivityInfo>
                  <div style={{ textAlign: 'right' }}>
                    <TSSValue tss={activity.tss}>
                      {activity.tss}
                    </TSSValue>
                    <div style={{ fontSize: '0.8rem', color: '#666' }}>
                      {getTSSStatus(activity.tss)}
                    </div>
                  </div>
                </ActivityItem>
              ))
            ) : (
              <EmptyMessage>
                Ingen aktiviteter med EPOC/TSS data i valgt periode.
              </EmptyMessage>
            )}
          </ActivityList>
        </>
      ) : (
        <EmptyMessage>
          Ingen EPOC/TSS data tilgjengelig for valgt periode.
        </EmptyMessage>
      )}
    </Container>
  );
};

export default TrainingStressPage; 