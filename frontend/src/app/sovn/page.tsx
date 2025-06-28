'use client';

import { useEffect, useState } from 'react';
import styled from 'styled-components';
import { healthApi } from '../../utils/api';
import { Card, Title, Text, Metric, Grid } from "@tremor/react";

const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
`;

const Header = styled.header`
  margin-bottom: 2rem;
`;

const DatePickerContainer = styled.div`
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
  color: red;
  padding: 1rem;
  border: 1px solid red;
  border-radius: 4px;
`;

// Hjelpefunksjon for å formatere sekunder til HH:MM
const formatDuration = (seconds: number) => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}t ${minutes}m`;
};

export default function HealthPage() {
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [sleepData, setSleepData] = useState<any>(null);
  const [stressData, setStressData] = useState<any>(null);
  const [hrvData, setHrvData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const [sleep, stress, hrv] = await Promise.all([
          healthApi.getSleep(selectedDate).catch(e => { console.error("Sleep fetch error:", e); return null; }),
          healthApi.getStress(selectedDate).catch(e => { console.error("Stress fetch error:", e); return null; }),
          healthApi.getHrv(selectedDate).catch(e => { console.error("HRV fetch error:", e); return null; })
        ]);
        console.log("Mottatt søvndata:", sleep);
        setSleepData(sleep);
        setStressData(stress);
        setHrvData(hrv);
      } catch (e: any) {
        setError("Kunne ikke laste helsedata.");
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [selectedDate]);

  return (
    <Container>
      <Header>
        <Title>Daglig Helseoversikt</Title>
      </Header>

      <DatePickerContainer>
        <Text>Velg dato</Text>
        <input
          type="date"
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          style={{ padding: '0.5rem', borderRadius: '4px', border: '1px solid #ccc' }}
        />
      </DatePickerContainer>

      {loading ? (
        <LoadingSpinner />
      ) : error ? (
        <ErrorMessage>{error}</ErrorMessage>
      ) : (
        <Grid>
          <Card>
            <Title>Søvn</Title>
            {sleepData ? (
              <>
                <Text>Total søvn (sekunder)</Text>
                <Metric>{sleepData.daily_sleep_dto.sleep_time_seconds}</Metric>
                <Text>Søvnscore</Text>
                <Metric>{sleepData.daily_sleep_dto.sleep_scores.overall.value}</Metric>
              </>
            ) : (
              <Text>Ingen søvndata tilgjengelig.</Text>
            )}
          </Card>

          <Card>
            <Title>Stress</Title>
            {stressData && stressData.daily_stress_dto ? (
              <>
                <Text>Gjennomsnittlig stressnivå</Text>
                <Metric>{stressData.daily_stress_dto.avg_stress_level}</Metric>
                 <Text>Maksimalt stressnivå</Text>
                <Metric>{stressData.daily_stress_dto.max_stress_level}</Metric>
              </>
            ) : (
              <Text>Ingen stressdata tilgjengelig.</Text>
            )}
          </Card>

          <Card>
            <Title>HRV (Pulsvariasjon)</Title>
            {hrvData ? (
              <>
                 <Text>Gjennomsnitt siste natt</Text>
                <Metric>{hrvData.hrv_summary.last_night_avg} ms</Metric>
                <Text>Status</Text>
                <Metric>{hrvData.hrv_summary.status}</Metric>
              </>
            ) : (
              <Text>Ingen HRV-data tilgjengelig.</Text>
            )}
          </Card>
        </Grid>
      )}
    </Container>
  );
} 