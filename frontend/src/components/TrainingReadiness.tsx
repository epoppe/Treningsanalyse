'use client';

import React, { useState, useEffect } from 'react';
import styled from 'styled-components';
import { activitiesApi } from '../utils/api';

interface TrainingReadinessData {
  date: string;
  total_score: number;
  readiness_status: string;
  components: {
    sleep_score: number;
    hrv_score: number;
    form_score: number;
  };
  details: {
    sleep_data: any[];
    hrv_data: any[];
    activity_data: any[];
    form_value?: number;
  };
}

interface TrainingReadinessProps {
  date?: string;
  showDetails?: boolean;
}

const Container = styled.div`
  background: white;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  margin-bottom: 20px;
`;

const Title = styled.h2`
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0 0 8px 0;
  color: #1f2937;
`;

const DateInfo = styled.div`
  font-size: 0.875rem;
  color: #6b7280;
  margin-bottom: 16px;
`;

const DailyBadge = styled.span`
  display: inline-block;
  background: #3b82f6;
  color: white;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 500;
  margin-left: 8px;
`;

const ScoreContainer = styled.div`
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
`;

const ScoreCircle = styled.div<{ score: number }>`
  width: 80px;
  height: 80px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  font-weight: bold;
  color: white;
  background: ${({ score }) => {
    if (score >= 80) return '#10b981'; // Grønn
    if (score >= 60) return '#3b82f6'; // Blå
    if (score >= 40) return '#f59e0b'; // Gul
    if (score >= 20) return '#ef4444'; // Rød
    return '#6b7280'; // Grå
  }};
`;

const ScoreInfo = styled.div`
  flex: 1;
`;

const ScoreValue = styled.div`
  font-size: 2rem;
  font-weight: bold;
  color: #1f2937;
  margin-bottom: 4px;
`;

const ScoreLabel = styled.div`
  font-size: 1rem;
  color: #6b7280;
  text-transform: capitalize;
`;

const StatusBadge = styled.span<{ status: string }>`
  display: inline-block;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 0.875rem;
  font-weight: 500;
  text-transform: capitalize;
  background: ${({ status }) => {
    switch (status) {
      case 'optimal': return '#dcfce7';
      case 'good': return '#dbeafe';
      case 'moderate': return '#fef3c7';
      case 'poor': return '#fee2e2';
      case 'very_poor': return '#f3f4f6';
      default: return '#f3f4f6';
    }
  }};
  color: ${({ status }) => {
    switch (status) {
      case 'optimal': return '#166534';
      case 'good': return '#1e40af';
      case 'moderate': return '#92400e';
      case 'poor': return '#991b1b';
      case 'very_poor': return '#374151';
      default: return '#374151';
    }
  }};
`;

const ComponentsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-top: 20px;
  
  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
`;

const ComponentCard = styled.div`
  background: #f9fafb;
  border-radius: 8px;
  padding: 16px;
  border-left: 4px solid #3b82f6;
`;

const ComponentTitle = styled.h3`
  font-size: 0.875rem;
  font-weight: 600;
  color: #374151;
  margin: 0 0 8px 0;
  text-transform: capitalize;
`;

const ComponentScore = styled.div`
  font-size: 1.5rem;
  font-weight: bold;
  color: #1f2937;
`;

const ComponentWeight = styled.div`
  font-size: 0.75rem;
  color: #9ca3af;
  margin-top: 4px;
`;

const FormValueInfo = styled.div`
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #e5e7eb;
  font-size: 0.75rem;
  color: #6b7280;
`;

const FormExplanation = styled.div`
  margin-top: 4px;
  font-size: 0.7rem;
  color: #9ca3af;
`;

const LoadingSpinner = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  height: 200px;
  color: #6b7280;
`;

const ErrorMessage = styled.div`
  color: #ef4444;
  text-align: center;
  padding: 20px;
`;

const Recommendation = styled.div`
  background: #f0f9ff;
  border: 1px solid #0ea5e9;
  border-radius: 8px;
  padding: 16px;
  margin-top: 16px;
  color: #0c4a6e;
  font-size: 0.875rem;
`;

const getStatusText = (status: string): string => {
  const statusMap: { [key: string]: string } = {
    optimal: 'Optimal',
    good: 'God',
    moderate: 'Moderat',
    poor: 'Dårlig',
    very_poor: 'Svært dårlig',
    unknown: 'Ukjent'
  };
  return statusMap[status] || status;
};

const getRecommendation = (status: string): string => {
  const recommendations: { [key: string]: string } = {
    optimal: 'Du er klar for intensiv trening. Gå for det!',
    good: 'Du kan gjøre moderat til intensiv trening. Lytt til kroppen.',
    moderate: 'Gjør lett til moderat trening. Fokuser på teknikk og form.',
    poor: 'Gjør lett trening eller hvile. Prioriter recovery.',
    very_poor: 'Ta en hviledag. Fokuser på søvn og recovery.',
    unknown: 'Ikke nok data til å gi anbefaling.'
  };
  return recommendations[status] || 'Ingen anbefaling tilgjengelig.';
};

export default function TrainingReadiness({ date, showDetails = true }: TrainingReadinessProps) {
  const [readinessData, setReadinessData] = useState<TrainingReadinessData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchReadiness = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const response = await activitiesApi.getTrainingReadiness(date);
        setReadinessData(response.data || response);
      } catch (err) {
        console.error('Feil ved henting av training readiness:', err);
        setError('Kunne ikke hente training readiness data');
      } finally {
        setLoading(false);
      }
    };

    fetchReadiness();
  }, [date]);

  if (loading) {
    return (
      <Container>
        <Title>Training Readiness</Title>
        <LoadingSpinner>Laster training readiness...</LoadingSpinner>
      </Container>
    );
  }

  if (error) {
    return (
      <Container>
        <Title>Training Readiness</Title>
        <ErrorMessage>{error}</ErrorMessage>
      </Container>
    );
  }

  if (!readinessData) {
    return (
      <Container>
        <Title>Training Readiness</Title>
        <ErrorMessage>Ingen data tilgjengelig</ErrorMessage>
      </Container>
    );
  }

  const { total_score, readiness_status, components } = readinessData;

  return (
    <Container>
      <Title>
        Daglig Training Readiness
        <DailyBadge>Daglig</DailyBadge>
      </Title>
      <DateInfo>
        Score for {new Date(readinessData.date).toLocaleDateString('nb-NO', {
          weekday: 'long',
          year: 'numeric',
          month: 'long',
          day: 'numeric'
        })}
      </DateInfo>
      
      <ScoreContainer>
        <ScoreCircle score={total_score}>
          {Math.round(total_score)}
        </ScoreCircle>
        <ScoreInfo>
          <ScoreValue>{Math.round(total_score)}/100</ScoreValue>
          <ScoreLabel>
            <StatusBadge status={readiness_status}>
              {getStatusText(readiness_status)}
            </StatusBadge>
          </ScoreLabel>
        </ScoreInfo>
      </ScoreContainer>

      <Recommendation>
        <strong>Anbefaling:</strong> {getRecommendation(readiness_status)}
      </Recommendation>

      {showDetails && (
        <ComponentsGrid>
          <ComponentCard>
            <ComponentTitle>Søvn</ComponentTitle>
            <ComponentScore>{Math.round(components.sleep_score)}</ComponentScore>
            <ComponentWeight>15% vekt</ComponentWeight>
          </ComponentCard>
          
          <ComponentCard>
            <ComponentTitle>HRV</ComponentTitle>
            <ComponentScore>{Math.round(components.hrv_score)}</ComponentScore>
            <ComponentWeight>15% vekt</ComponentWeight>
          </ComponentCard>
          
          <ComponentCard>
            <ComponentTitle>Form / TSB</ComponentTitle>
            <ComponentScore>{Math.round(components.form_score)}</ComponentScore>
            <ComponentWeight>70% vekt</ComponentWeight>
            {readinessData.details?.form_value !== undefined && (
              <FormValueInfo>
                TSB: {readinessData.details.form_value.toFixed(1)}
                <FormExplanation>
                  {readinessData.details.form_value < -15 ? '🔴 Høy fatigue' :
                   readinessData.details.form_value < -5 ? '🟡 Moderat fatigue' :
                   readinessData.details.form_value < 5 ? '🟢 Balansert' :
                   readinessData.details.form_value < 15 ? '🟢 Godt restituert' :
                   '🟢 Meget frisk'}
                </FormExplanation>
              </FormValueInfo>
            )}
          </ComponentCard>
        </ComponentsGrid>
      )}
    </Container>
  );
} 