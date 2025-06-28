'use client';

import { useState, useEffect } from 'react';
import styled from 'styled-components';
import dynamic from 'next/dynamic';
import HealthDataSyncPanel from '../../components/HealthDataSyncPanel';
import { analysisApi } from '../../utils/api';
import { HrvData } from '../../types/hrv';

const HrvChart = dynamic(() => import('../../components/HrvChart'), {
  loading: () => <p>Laster diagram...</p>,
  ssr: false,
});

const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
`;

const Header = styled.header`
  margin-bottom: 2rem;
  text-align: center;
`;

const Title = styled.h1`
  color: #2c3e50;
  font-size: 2rem;
  margin-bottom: 0.5rem;
`;

const Subtitle = styled.p`
  color: #666;
  font-size: 1.125rem;
`;

const FilterContainer = styled.div`
  display: flex;
  justify-content: center;
  gap: 0.5rem;
  margin-bottom: 2rem;
`;

const FilterButton = styled.button<{ $active: boolean }>`
  padding: 0.5rem 1rem;
  border: 1px solid ${({ $active }) => ($active ? '#3498db' : '#ddd')};
  background: ${({ $active }) => ($active ? '#3498db' : 'white')};
  color: ${({ $active }) => ($active ? 'white' : '#333')};
  border-radius: 5px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.2s ease-in-out;

  &:hover {
    background: ${({ $active }) => ($active ? '#2980b9' : '#f0f0f0')};
  }
`;

const LoadingSpinner = styled.div`
  border: 4px solid #f3f3f3;
  border-top: 4px solid #3498db;
  border-radius: 50%;
  width: 24px;
  height: 24px;
  animation: spin 1s linear infinite;
  margin: 0 auto;

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
`;

const HrvPage = () => {
  const [hrvData, setHrvData] = useState<HrvData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState('3m');
  
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const fetchHrvData = async (start: string, end: string) => {
    if (!start || !end) return;
    try {
      setLoading(true);
      setError(null);
      const response = await analysisApi.getHrv(start, end);
      setHrvData(response.hrv_data);
    } catch (err) {
      setError('Kunne ikke hente HRV-data.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleFilterClick = (filter: string) => {
    setActiveFilter(filter);
    const end = new Date();
    const start = new Date();

    switch (filter) {
      case '3m':
        start.setMonth(start.getMonth() - 3);
        break;
      case '6m':
        start.setMonth(start.getMonth() - 6);
        break;
      case 'ytd':
        start.setFullYear(start.getFullYear(), 0, 1);
        break;
      case '12m':
        start.setFullYear(start.getFullYear() - 1);
        break;
      case '3y':
        start.setFullYear(start.getFullYear() - 3);
        break;
      case 'all':
        start.setFullYear(start.getFullYear() - 10);
        break;
    }
    const newStartDate = start.toISOString().split('T')[0];
    const newEndDate = end.toISOString().split('T')[0];
    setStartDate(newStartDate);
    setEndDate(newEndDate);
  };

  useEffect(() => {
    handleFilterClick('3m'); // Sett default til 3 måneder
  }, []);

  useEffect(() => {
    fetchHrvData(startDate, endDate);
  }, [startDate, endDate]);

  const handleSyncComplete = () => {
    // Oppdater HRV-data når synkronisering er fullført
    fetchHrvData(startDate, endDate);
  };

  return (
    <Container>
      <Header>
        <Title>HRV Status</Title>
        <Subtitle>Analyser din hjertevariabilitet over tid</Subtitle>
      </Header>
      
      <HealthDataSyncPanel onSyncComplete={handleSyncComplete} />

      <FilterContainer>
        <FilterButton $active={activeFilter === '3m'} onClick={() => handleFilterClick('3m')}>Siste 3 mnd</FilterButton>
        <FilterButton $active={activeFilter === '6m'} onClick={() => handleFilterClick('6m')}>Siste 6 mnd</FilterButton>
        <FilterButton $active={activeFilter === 'ytd'} onClick={() => handleFilterClick('ytd')}>År til dato</FilterButton>
        <FilterButton $active={activeFilter === '12m'} onClick={() => handleFilterClick('12m')}>Siste 12 mnd</FilterButton>
        <FilterButton $active={activeFilter === '3y'} onClick={() => handleFilterClick('3y')}>Siste 3 år</FilterButton>
        <FilterButton $active={activeFilter === 'all'} onClick={() => handleFilterClick('all')}>All historikk</FilterButton>
      </FilterContainer>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '2rem' }}>
          <LoadingSpinner />
          <p>Laster HRV-data...</p>
        </div>
      ) : error ? (
        <p style={{ color: 'red', textAlign: 'center' }}>{error}</p>
      ) : (
        <HrvChart hrvData={hrvData} />
      )}
    </Container>
  );
};

export default HrvPage; 