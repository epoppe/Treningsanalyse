'use client';

import React, { useState } from 'react';
import styled from 'styled-components';
import { activitiesApi } from '../utils/api';

const PanelContainer = styled.div`
  background-color: #f0f2f5;
  padding: 24px;
  border-radius: 8px;
  margin-bottom: 24px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
`;

const Title = styled.h2`
  margin-top: 0;
  margin-bottom: 16px;
  font-size: 1.5rem;
  color: #333;
`;

const FormRow = styled.div`
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  align-items: center;
`;

const Label = styled.label`
  font-weight: 500;
  color: #555;
`;

const Input = styled.input`
  padding: 8px 12px;
  border-radius: 4px;
  border: 1px solid #ccc;
  font-size: 1rem;
`;

const Button = styled.button`
  padding: 10px 16px;
  border-radius: 4px;
  border: none;
  background-color: #007bff;
  color: white;
  font-size: 1rem;
  cursor: pointer;
  transition: background-color 0.2s;

  &:hover {
    background-color: #0056b3;
  }

  &:disabled {
    background-color: #a0c7e4;
    cursor: not-allowed;
  }
`;

const StatusMessage = styled.p`
  margin-top: 16px;
  font-style: italic;
  color: #555;
`;

const DataSyncPanel: React.FC = () => {
    const today = new Date().toISOString().split('T')[0];
    const [startDate, setStartDate] = useState(() => {
        const date = new Date();
        date.setDate(date.getDate() - 30); // Siste 30 dager
        return date.toISOString().split('T')[0];
    });
    const [endDate, setEndDate] = useState(today);
    const [isLoading, setIsLoading] = useState(false);
    const [status, setStatus] = useState('');

    const handleSync = async () => {
        setIsLoading(true);
        setStatus('Starter synkronisering...');
        try {
            console.log('Sender synkroniseringsforespørsel med datoer:', {
                startDate,
                endDate,
                startDateType: typeof startDate,
                endDateType: typeof endDate
            });
            const response = await activitiesApi.syncActivities(startDate, endDate);
            console.log('Mottok respons fra backend:', response);
            if (response.message) {
                setStatus(response.message);
            } else {
                setStatus('Synkronisering startet i bakgrunnen! Data vil bli tilgjengelig fortløpende.');
            }
        } catch (error) {
            console.error("Synkroniseringsfeil:", error);
            setStatus('En feil oppstod under synkronisering. Sjekk konsollen.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <PanelContainer>
            <Title>Synkroniser Treningsdata</Title>
            <p>Velg en tidsperiode for å laste ned nye treningsdata fra Garmin Connect. Systemet vil automatisk hoppe over dager som allerede er lagret.</p>
            <FormRow>
                <Label htmlFor="start-date">Fra dato:</Label>
                <Input
                    type="date"
                    id="start-date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    disabled={isLoading}
                />
                <Label htmlFor="end-date">Til dato:</Label>
                <Input
                    type="date"
                    id="end-date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    disabled={isLoading}
                />
            </FormRow>
            <Button onClick={handleSync} disabled={isLoading}>
                {isLoading ? 'Synkroniserer...' : 'Start Synkronisering'}
            </Button>
            {status && <StatusMessage>{status}</StatusMessage>}
        </PanelContainer>
    );
};

export default DataSyncPanel; 