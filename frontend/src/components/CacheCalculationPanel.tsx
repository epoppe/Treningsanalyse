'use client';

import { useState } from 'react';
import styled from 'styled-components';
import { BASE_URL } from '../utils/api';

const Panel = styled.div`
  background: white;
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 2rem;
`;

const Title = styled.h3`
  margin: 0 0 1rem 0;
  color: #2c3e50;
`;

const Description = styled.p`
  color: #7f8c8d;
  margin-bottom: 1rem;
  font-size: 0.9rem;
`;

const ButtonContainer = styled.div`
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
`;

const Button = styled.button<{ $variant?: 'primary' | 'secondary' }>`
  background-color: ${props => props.$variant === 'secondary' ? '#95a5a6' : '#3498db'};
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s ease-in-out;

  &:hover {
    background-color: ${props => props.$variant === 'secondary' ? '#7f8c8d' : '#2980b9'};
  }

  &:disabled {
    background-color: #bdc3c7;
    cursor: not-allowed;
  }
`;

const StatsContainer = styled.div`
  background: #ecf0f1;
  padding: 1rem;
  border-radius: 4px;
  margin-top: 1rem;
`;

const StatRow = styled.div`
  display: flex;
  justify-content: space-between;
  padding: 0.5rem 0;
  border-bottom: 1px solid #bdc3c7;

  &:last-child {
    border-bottom: none;
  }
`;

const StatLabel = styled.span`
  color: #2c3e50;
  font-weight: 500;
`;

const StatValue = styled.span`
  color: #7f8c8d;
`;

const StatusMessage = styled.div<{ $type: 'info' | 'success' | 'error' }>`
  padding: 1rem;
  border-radius: 4px;
  margin-top: 1rem;
  background-color: ${props => {
    switch (props.$type) {
      case 'success': return '#d4edda';
      case 'error': return '#f8d7da';
      default: return '#d1ecf1';
    }
  }};
  color: ${props => {
    switch (props.$type) {
      case 'success': return '#155724';
      case 'error': return '#721c24';
      default: return '#0c5460';
    }
  }};
  border: 1px solid ${props => {
    switch (props.$type) {
      case 'success': return '#c3e6cb';
      case 'error': return '#f5c6cb';
      default: return '#bee5eb';
    }
  }};
`;

interface CacheStats {
  total_activities: number;
  cached_values: {
    tss: { count: number; percentage: number };
    power: { count: number; percentage: number };
    running_economy: { count: number; percentage: number };
    negative_split: { count: number; percentage: number };
    decoupling: { count: number; percentage: number };
  };
}

export default function CacheCalculationPanel() {
  const [isCalculating, setIsCalculating] = useState(false);
  const [stats, setStats] = useState<CacheStats | null>(null);
  const [message, setMessage] = useState<{ type: 'info' | 'success' | 'error'; text: string } | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const fetchStats = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${BASE_URL}/api/cache/stats`);
      const data = await response.json();
      setStats(data);
    } catch (error) {
      console.error('Feil ved henting av cache-statistikk:', error);
      setMessage({ type: 'error', text: 'Kunne ikke hente cache-statistikk' });
    } finally {
      setIsLoading(false);
    }
  };

  const calculateAll = async (onlyMissing: boolean = true) => {
    setIsCalculating(true);
    setMessage({ type: 'info', text: 'Starter cache-beregning i bakgrunnen...' });

    try {
      const response = await fetch(
        `${BASE_URL}/api/cache/calculate-all?only_missing=${onlyMissing}`,
        { method: 'POST' }
      );

      if (response.ok) {
        setMessage({
          type: 'success',
          text: 'Cache-beregning startet! Dette kan ta noen minutter. Refresh siden for å se oppdatert statistikk.'
        });
        
        // Vent 5 sekunder og hent statistikk på nytt
        setTimeout(() => {
          fetchStats();
        }, 5000);
      } else {
        setMessage({ type: 'error', text: 'Feil ved start av cache-beregning' });
      }
    } catch (error) {
      console.error('Feil ved cache-beregning:', error);
      setMessage({ type: 'error', text: 'Kunne ikke starte cache-beregning' });
    } finally {
      setIsCalculating(false);
    }
  };

  return (
    <Panel>
      <Title>⚡ Cache-beregninger</Title>
      <Description>
        Beregn og lagre alle verdier (TSS, Power, Løpsøkonomi, etc.) i databasen for raskere lasting.
        Dette trenger kun å gjøres én gang, eller når du har nye aktiviteter.
      </Description>

      <ButtonContainer>
        <Button onClick={() => calculateAll(true)} disabled={isCalculating}>
          Beregn manglende verdier
        </Button>
        <Button onClick={() => calculateAll(false)} $variant="secondary" disabled={isCalculating}>
          Beregn alle på nytt
        </Button>
        <Button onClick={fetchStats} $variant="secondary" disabled={isCalculating}>
          Oppdater statistikk
        </Button>
      </ButtonContainer>

      {message && (
        <StatusMessage $type={message.type}>
          {message.text}
        </StatusMessage>
      )}

      {stats && stats.cached_values && (
        <StatsContainer>
          <StatRow>
            <StatLabel>Totalt aktiviteter:</StatLabel>
            <StatValue>{stats.total_activities}</StatValue>
          </StatRow>
          <StatRow>
            <StatLabel>TSS (Training Stress):</StatLabel>
            <StatValue>
              {stats.cached_values.tss?.count || 0} ({stats.cached_values.tss?.percentage || 0}%)
            </StatValue>
          </StatRow>
          <StatRow>
            <StatLabel>Power (Løpekraft):</StatLabel>
            <StatValue>
              {stats.cached_values.power?.count || 0} ({stats.cached_values.power?.percentage || 0}%)
            </StatValue>
          </StatRow>
          <StatRow>
            <StatLabel>Løpsøkonomi:</StatLabel>
            <StatValue>
              {stats.cached_values.running_economy?.count || 0} ({stats.cached_values.running_economy?.percentage || 0}%)
            </StatValue>
          </StatRow>
          <StatRow>
            <StatLabel>Negative Split:</StatLabel>
            <StatValue>
              {stats.cached_values.negative_split?.count || 0} ({stats.cached_values.negative_split?.percentage || 0}%)
            </StatValue>
          </StatRow>
          <StatRow>
            <StatLabel>Decoupling:</StatLabel>
            <StatValue>
              {stats.cached_values.decoupling?.count || 0} ({stats.cached_values.decoupling?.percentage || 0}%)
            </StatValue>
          </StatRow>
        </StatsContainer>
      )}
    </Panel>
  );
}

