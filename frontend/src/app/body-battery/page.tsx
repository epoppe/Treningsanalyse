'use client';

import React, { useState, useEffect } from 'react';
import styled from 'styled-components';
import { api } from '../../utils/api';

// Styled components
const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
`;

const Title = styled.h1`
  color: #2c3e50;
  text-align: center;
  margin-bottom: 2rem;
  font-size: 2.5rem;
`;

const DateSelector = styled.div`
  display: flex;
  justify-content: center;
  gap: 1rem;
  margin-bottom: 2rem;
  align-items: center;
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
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 2rem;
  margin-bottom: 2rem;
`;

const MetricCard = styled.div`
  background: white;
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  border-left: 4px solid #3498db;
`;

const MetricTitle = styled.h3`
  color: #2c3e50;
  margin-bottom: 1rem;
  font-size: 1.2rem;
`;

const MetricValue = styled.div`
  font-size: 2rem;
  font-weight: bold;
  color: #3498db;
  margin-bottom: 0.5rem;
`;

const MetricLabel = styled.div`
  color: #666;
  font-size: 0.9rem;
`;

const ChartContainer = styled.div`
  background: white;
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 2rem;
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

// Types
interface BodyBatteryData {
  date: string;
  body_battery_charged: number;
  body_battery_drained: number;
  body_battery_charged_start: number;
  body_battery_drained_start: number;
  net_charge: number;
}

const BodyBatteryPage: React.FC = () => {
  const [selectedDate, setSelectedDate] = useState<string>(
    new Date().toISOString().split('T')[0]
  );
  const [bodyBatteryData, setBodyBatteryData] = useState<BodyBatteryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchBodyBatteryData = async (date: string) => {
    setLoading(true);
    setError(null);
    
    try {
      const data = await api.getBodyBattery(date);
      setBodyBatteryData(data);
    } catch (err: any) {
      if (err.response?.status === 404) {
        setError('Ingen body battery data tilgjengelig for valgt dato.');
      } else {
        setError(err.message || 'En feil oppstod ved henting av data.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBodyBatteryData(selectedDate);
  }, [selectedDate]);

  const handleDateChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSelectedDate(event.target.value);
  };

  const formatBatteryLevel = (level: number) => {
    if (level === null || level === undefined) return 'N/A';
    return `${level}%`;
  };

  const getBatteryColor = (level: number) => {
    if (level >= 80) return '#27ae60'; // Grønn
    if (level >= 60) return '#f39c12'; // Oransje
    if (level >= 40) return '#e67e22'; // Mørk oransje
    return '#e74c3c'; // Rød
  };

  const getBatteryStatus = (level: number) => {
    if (level >= 80) return 'Høy';
    if (level >= 60) return 'Moderat';
    if (level >= 40) return 'Lav';
    return 'Kritisk';
  };

  return (
    <Container>
      <Title>🔋 Body Battery</Title>
      
      <DateSelector>
        <label htmlFor="date-selector">Velg dato:</label>
        <DateInput
          id="date-selector"
          type="date"
          value={selectedDate}
          onChange={handleDateChange}
          max={new Date().toISOString().split('T')[0]}
        />
        <Button onClick={() => fetchBodyBatteryData(selectedDate)} disabled={loading}>
          {loading ? 'Henter...' : 'Oppdater'}
        </Button>
      </DateSelector>

      {error && <ErrorMessage>{error}</ErrorMessage>}

      {loading ? (
        <LoadingSpinner />
      ) : bodyBatteryData ? (
        <>
          <MetricsGrid>
            <MetricCard>
              <MetricTitle>Startnivå (Oppladet)</MetricTitle>
              <MetricValue style={{ color: getBatteryColor(bodyBatteryData.body_battery_charged_start || 0) }}>
                {formatBatteryLevel(bodyBatteryData.body_battery_charged_start)}
              </MetricValue>
              <MetricLabel>
                Status: {getBatteryStatus(bodyBatteryData.body_battery_charged_start || 0)}
              </MetricLabel>
            </MetricCard>

            <MetricCard>
              <MetricTitle>Startnivå (Utladet)</MetricTitle>
              <MetricValue style={{ color: getBatteryColor(bodyBatteryData.body_battery_drained_start || 0) }}>
                {formatBatteryLevel(bodyBatteryData.body_battery_drained_start)}
              </MetricValue>
              <MetricLabel>
                Status: {getBatteryStatus(bodyBatteryData.body_battery_drained_start || 0)}
              </MetricLabel>
            </MetricCard>

            <MetricCard>
              <MetricTitle>Total Oppladning</MetricTitle>
              <MetricValue style={{ color: '#27ae60' }}>
                {bodyBatteryData.body_battery_charged || 0}%
              </MetricValue>
              <MetricLabel>Oppladet gjennom dagen</MetricLabel>
            </MetricCard>

            <MetricCard>
              <MetricTitle>Total Utladning</MetricTitle>
              <MetricValue style={{ color: '#e74c3c' }}>
                {bodyBatteryData.body_battery_drained || 0}%
              </MetricValue>
              <MetricLabel>Utladet gjennom dagen</MetricLabel>
            </MetricCard>

            <MetricCard>
              <MetricTitle>Netto Lading</MetricTitle>
              <MetricValue style={{ 
                color: bodyBatteryData.net_charge >= 0 ? '#27ae60' : '#e74c3c' 
              }}>
                {bodyBatteryData.net_charge >= 0 ? '+' : ''}{bodyBatteryData.net_charge}%
              </MetricValue>
              <MetricLabel>
                {bodyBatteryData.net_charge >= 0 ? 'Positiv netto lading' : 'Negativ netto lading'}
              </MetricLabel>
            </MetricCard>
          </MetricsGrid>

          <ChartContainer>
            <MetricTitle>Body Battery Oversikt</MetricTitle>
            <div style={{ 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'center',
              marginTop: '1rem'
            }}>
              <div>
                <strong>Dato:</strong> {new Date(bodyBatteryData.date).toLocaleDateString('nb-NO')}
              </div>
              <div>
                <strong>Netto endring:</strong> {bodyBatteryData.net_charge}%
              </div>
            </div>
            
            {/* Enkel visualisering av body battery */}
            <div style={{ 
              marginTop: '1rem',
              padding: '1rem',
              backgroundColor: '#f8f9fa',
              borderRadius: '4px'
            }}>
              <div style={{ marginBottom: '0.5rem' }}>
                <strong>Body Battery Status:</strong>
              </div>
              <div style={{ 
                display: 'flex', 
                gap: '1rem',
                flexWrap: 'wrap'
              }}>
                <div>
                  <span style={{ color: '#27ae60' }}>●</span> Start (Oppladet): {formatBatteryLevel(bodyBatteryData.body_battery_charged_start)}
                </div>
                <div>
                  <span style={{ color: '#e74c3c' }}>●</span> Start (Utladet): {formatBatteryLevel(bodyBatteryData.body_battery_drained_start)}
                </div>
                <div>
                  <span style={{ color: '#3498db' }}>●</span> Oppladet: {bodyBatteryData.body_battery_charged || 0}%
                </div>
                <div>
                  <span style={{ color: '#e67e22' }}>●</span> Utladet: {bodyBatteryData.body_battery_drained || 0}%
                </div>
              </div>
            </div>
          </ChartContainer>
        </>
      ) : (
        <EmptyMessage>
          Ingen body battery data tilgjengelig for valgt dato.
        </EmptyMessage>
      )}
    </Container>
  );
};

export default BodyBatteryPage; 