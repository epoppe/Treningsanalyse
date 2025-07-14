'use client';

import { useEffect, useState } from 'react';
import styled from 'styled-components';
import HrvChart from '../../components/HrvChart';
import { api, BASE_URL } from '../../utils/api';

const PageContainer = styled.div`
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
`;

const Title = styled.h1`
  color: #2c3e50;
  margin-bottom: 2rem;
  text-align: center;
`;

const LoadingContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  height: 200px;
  font-size: 1.2rem;
  color: #666;
`;

const ErrorContainer = styled.div`
  background: #fee2e2;
  color: #dc2626;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 2rem;
  text-align: center;
`;

const FilterContainer = styled.div`
  background: white;
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 2rem;
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  align-items: center;
`;

const FilterGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
`;

const Label = styled.label`
  font-weight: 500;
  color: #374151;
  font-size: 0.9rem;
`;

const Input = styled.input`
  padding: 0.5rem;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 0.9rem;
  
  &:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 1px #3b82f6;
  }
`;

const Button = styled.button`
  background-color: #3b82f6;
  color: white;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
  height: fit-content;
  margin-top: 1.5rem;
  
  &:hover {
    background-color: #2563eb;
  }
  
  &:disabled {
    background-color: #9ca3af;
    cursor: not-allowed;
  }
`;

interface HrvData {
  date: string;
  last_night_avg: number;
  last_night_5_min_high: number;
  baseline_low_upper: number;
  baseline_balanced_lower: number;
  baseline_balanced_upper: number;
  status: string;
  rolling_avg_7d: number;
}

interface HrvResponse {
  hrv_data: HrvData[];
  total_records: number;
}

export default function HrvPage() {
  const [hrvData, setHrvData] = useState<HrvData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  // Sett standard datoer - siste 6 måneder
  useEffect(() => {
    const today = new Date();
    const sixMonthsAgo = new Date();
    sixMonthsAgo.setMonth(today.getMonth() - 6);
    
    // Sørg for at vi ikke går før 2023
    const minDate = new Date('2023-01-01');
    const actualStartDate = sixMonthsAgo < minDate ? minDate : sixMonthsAgo;
    
    setStartDate(actualStartDate.toISOString().split('T')[0]);
    setEndDate(today.toISOString().split('T')[0]);
  }, []);

  const fetchHrvData = async (start?: string, end?: string) => {
    try {
      setLoading(true);
      setError(null);
      
      const params = new URLSearchParams();
      if (start) params.append('start_date', start);
      if (end) params.append('end_date', end);
      
      const response = await fetch(`${BASE_URL}/api/analysis/hrv?${params}`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data: HrvResponse = await response.json();
      
      console.log('HRV API Response:', data);
      console.log('HRV data length:', data.hrv_data?.length);
      
      if (data.hrv_data && data.hrv_data.length > 0) {
        // Normaliser datofelt til kun dato-del (fjern timestamp)
        const normalizedData = data.hrv_data.map(item => ({
          ...item,
          date: item.date.split('T')[0] // Fjern timestamp-del fra dato
        }));
        console.log('Normalized HRV data:', normalizedData);
        setHrvData(normalizedData);
      } else {
        setHrvData([]);
        setError('Ingen HRV-data funnet for valgt periode. HRV-data er kun tilgjengelig fra 2023 og fremover.');
      }
    } catch (err) {
      console.error('Feil ved henting av HRV-data:', err);
      setError('Det oppstod en feil ved henting av HRV-data. Vennligst prøv igjen.');
      setHrvData([]);
    } finally {
      setLoading(false);
    }
  };

  // Hent data når komponenten laster og når datoer er satt
  useEffect(() => {
    if (startDate && endDate) {
      fetchHrvData(startDate, endDate);
    }
  }, [startDate, endDate]); // Avhengig av startDate og endDate

  const handleFilterSubmit = () => {
    if (startDate && endDate) {
      fetchHrvData(startDate, endDate);
    }
  };

  const handleLoadAll = () => {
    fetchHrvData(); // Uten datofilter
  };

  if (loading) {
    return (
      <PageContainer>
        <Title>HRV-analyse</Title>
        <LoadingContainer>
          Laster HRV-data...
        </LoadingContainer>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <Title>HRV-analyse</Title>
      
      <FilterContainer>
        <FilterGroup>
          <Label htmlFor="startDate">Fra dato:</Label>
          <Input
            id="startDate"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            min="2023-01-01"
          />
        </FilterGroup>
        
        <FilterGroup>
          <Label htmlFor="endDate">Til dato:</Label>
          <Input
            id="endDate"
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            min="2023-01-01"
          />
        </FilterGroup>
        
        <Button onClick={handleFilterSubmit} disabled={!startDate || !endDate}>
          Filtrer periode
        </Button>
        
        <Button onClick={handleLoadAll}>
          Last alle data
        </Button>
      </FilterContainer>

      {error && (
        <ErrorContainer>
          {error}
        </ErrorContainer>
      )}

      {!error && hrvData.length > 0 && (
        <HrvChart 
          data={hrvData} 
          title="HRV (Heart Rate Variability) over tid"
        />
      )}

      {!error && hrvData.length === 0 && !loading && (
        <ErrorContainer>
          Ingen HRV-data funnet. HRV-data er kun tilgjengelig fra 2023 og fremover.
        </ErrorContainer>
      )}
    </PageContainer>
  );
} 