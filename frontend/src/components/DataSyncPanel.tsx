'use client';

import React, { useState, useEffect } from 'react';
import styled from 'styled-components';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { fetchActivities } from '@/store/slices/activitiesSlice';
import { api } from '@/utils/api';

const SyncPanelContainer = styled.div`
  background-color: #333;
  padding: 20px;
  border-radius: 8px;
  color: white;
  margin-bottom: 20px;
`;

const Title = styled.h2`
  margin-top: 0;
  color: #eee;
`;

const InputGroup = styled.div`
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 15px;
`;

const Label = styled.label`
  min-width: 70px;
`;

const Input = styled.input`
  padding: 8px;
  border-radius: 4px;
  border: 1px solid #555;
  background-color: #444;
  color: white;
`;

const Button = styled.button`
  background-color: #007bff;
  color: white;
  border: none;
  padding: 10px 15px;
  border-radius: 4px;
  cursor: pointer;
  width: 100%;
  font-size: 16px;

  &:hover {
    background-color: #0056b3;
  }

  &:disabled {
    background-color: #555;
    cursor: not-allowed;
  }
`;

const ButtonGroup = styled.div`
  display: flex;
  gap: 10px;
  margin-top: 10px;
`;

const StatusMessage = styled.p`
  margin-top: 15px;
  color: #aaa;
`;

const DataSyncPanel = () => {
  const dispatch = useAppDispatch();
  const [statusMessage, setStatusMessage] = useState<string>('');
  const [jobId, setJobId] = useState<string | null>(null);

  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  useEffect(() => {
    if (!jobId) return;

    const interval = setInterval(async () => {
      try {
        const statusData = await api.getSyncStatus(jobId);
        setStatusMessage(`Synkroniseringsstatus: ${statusData.status}`);

        if (statusData.status === 'completed' || statusData.status === 'failed') {
          clearInterval(interval);
          setJobId(null);
          if (statusData.status === 'completed') {
            setStatusMessage('Synkronisering fullført! Henter nye data...');
            dispatch(fetchActivities());
            setTimeout(() => setStatusMessage(''), 5000); // Fjerner melding etter 5 sek
          } else {
            setStatusMessage(`Feil under synkronisering: ${statusData.error}`);
          }
        }
      } catch (error) {
        clearInterval(interval);
        setJobId(null);
        setStatusMessage('Kunne ikke hente synkroniseringsstatus.');
      }
    }, 5000); // Sjekker status hvert 5. sekund

    return () => clearInterval(interval);
  }, [jobId, dispatch]);

  const handleSync = async () => {
    if (!startDate || !endDate) {
      alert('Vennligst velg både start- og sluttdato.');
      return;
    }
    try {
      setStatusMessage('Starter synkronisering...');
      const response = await api.syncActivities(startDate, endDate);
      setJobId(response.job_id);
    } catch (err: any) {
      console.error('Synkroniseringsfeil:', err);
      setStatusMessage('Kunne ikke starte synkronisering.');
    }
  };

  const handleSync30Days = async () => {
    try {
      setStatusMessage('Starter synkronisering for siste 30 dager...');
      const response = await api.syncRecentActivities();
      setJobId(response.job_id);
    } catch (err: any) {
      console.error('Feil ved synkronisering av siste 30 dager:', err);
      setStatusMessage('Kunne ikke starte synkronisering for 30 dager.');
    }
  };
  
  const isLoading = !!jobId;

  return (
    <SyncPanelContainer>
      <Title>Synkroniseringspanel</Title>
      <InputGroup>
        <Label>Fra dato:</Label>
        <Input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} disabled={isLoading} />
        <Label>Til dato:</Label>
        <Input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} disabled={isLoading} />
      </InputGroup>
      <ButtonGroup>
        <Button onClick={handleSync} disabled={isLoading || !startDate || !endDate}>
          {isLoading ? 'Opptatt...' : 'Synk valgt periode'}
        </Button>
        <Button onClick={handleSync30Days} disabled={isLoading}>
          {isLoading ? 'Opptatt...' : 'Synk siste 30 dager (force refresh)'}
        </Button>
      </ButtonGroup>
      {statusMessage && <StatusMessage>{statusMessage}</StatusMessage>}
    </SyncPanelContainer>
  );
};

export default DataSyncPanel; 