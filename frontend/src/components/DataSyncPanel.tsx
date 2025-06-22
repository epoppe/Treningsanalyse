'use client';

import React, { useState } from 'react';
import styled from 'styled-components';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { fetchActivities } from '@/store/slices/activitiesSlice';
import { activitiesApi } from '@/utils/api';

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

const StatusMessage = styled.p`
  margin-top: 15px;
  color: #aaa;
`;

const DataSyncPanel = () => {
  const dispatch = useAppDispatch();
  const { status, error } = useAppSelector((state) => state.activities);

  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const handleSync = async () => {
    if (!startDate || !endDate) {
      // Vi trenger ikke å dispatche en feil her, bare forhindre kjøring
      alert('Vennligst velg både start- og sluttdato.');
      return;
    }

    try {
      await activitiesApi.syncActivities(startDate, endDate);
      // Etter en vellykket synk, hent de oppdaterte aktivitetene
      dispatch(fetchActivities());
    } catch (err: any) {
      // Selve synk-kallet håndterer ikke Redux state, 
      // men vi kan logge feilen her for feilsøking.
      console.error('Synkroniseringsfeil:', err);
    }
  };
  
  const isLoading = status === 'loading';

  return (
    <SyncPanelContainer>
      <Title>Synkroniseringspanel</Title>
      <InputGroup>
        <Label>Fra dato:</Label>
        <Input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
        <Label>Til dato:</Label>
        <Input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
      </InputGroup>
      <Button onClick={handleSync} disabled={isLoading}>
        {isLoading ? 'Synkroniserer...' : 'Start Garmin-synk'}
      </Button>
      {error && <StatusMessage style={{ color: 'red' }}>Feil: {error}</StatusMessage>}
    </SyncPanelContainer>
  );
};

export default DataSyncPanel; 