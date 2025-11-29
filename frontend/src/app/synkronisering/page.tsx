'use client';

import { useState, useEffect } from 'react';
import styled from 'styled-components';
import { format, subDays, startOfDay, endOfDay } from 'date-fns';
import { nb } from 'date-fns/locale';
import { api } from '../../utils/api';
import CacheCalculationPanel from '../../components/CacheCalculationPanel';
import { useAppDispatch } from '@/store/hooks';
import { fetchActivities, fetchMoreActivities, fetchActivityCount } from '@/store/slices/activitiesSlice';

const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
`;

const Title = styled.h1`
  color: #2c3e50;
  margin-bottom: 2rem;
  text-align: center;
`;

const SyncSection = styled.div`
  background: white;
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 2rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
`;

const SectionTitle = styled.h2`
  color: #34495e;
  margin-bottom: 1rem;
  font-size: 1.5rem;
`;

const Button = styled.button<{ $primary?: boolean; $danger?: boolean; $disabled?: boolean }>`
  background-color: ${props => {
    if (props.$disabled) return '#bdc3c7';
    if (props.$danger) return '#e74c3c';
    if (props.$primary) return '#3498db';
    return '#ecf0f1';
  }};
  color: ${props => props.$disabled ? '#7f8c8d' : 'white'};
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 4px;
  cursor: ${props => props.$disabled ? 'not-allowed' : 'pointer'};
  font-size: 1rem;
  margin-right: 1rem;
  margin-bottom: 1rem;
  transition: all 0.2s ease-in-out;

  &:hover {
    background-color: ${props => {
      if (props.$disabled) return '#bdc3c7';
      if (props.$danger) return '#c0392b';
      if (props.$primary) return '#2980b9';
      return '#d5dbdb';
    }};
  }
`;

const StatusContainer = styled.div`
  margin-top: 1rem;
  padding: 1rem;
  border-radius: 4px;
  background-color: #f8f9fa;
  border-left: 4px solid #3498db;
`;

const StatusText = styled.div<{ $status: string }>`
  color: ${props => {
    switch (props.$status) {
      case 'completed': return '#27ae60';
      case 'failed': return '#e74c3c';
      case 'processing': return '#f39c12';
      default: return '#7f8c8d';
    }
  }};
  font-weight: 500;
`;

const ProgressBar = styled.div<{ $progress: number }>`
  width: 100%;
  height: 8px;
  background-color: #ecf0f1;
  border-radius: 4px;
  overflow: hidden;
  margin-top: 0.5rem;

  &::after {
    content: '';
    display: block;
    height: 100%;
    width: ${props => props.$progress}%;
    background-color: #3498db;
    transition: width 0.3s ease;
  }
`;

const DateInput = styled.input`
  padding: 0.5rem;
  border: 1px solid #bdc3c7;
  border-radius: 4px;
  margin-right: 1rem;
  font-size: 1rem;
`;

const DateLabel = styled.label`
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: #2c3e50;
`;

const DateContainer = styled.div`
  margin-bottom: 1rem;
`;

const QuickActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 2rem;
`;

const QuickActionButton = styled.button<{ $disabled?: boolean }>`
  background-color: ${props => props.$disabled ? '#bdc3c7' : '#2ecc71'};
  color: white;
  border: none;
  padding: 1rem 1.5rem;
  border-radius: 6px;
  cursor: ${props => props.$disabled ? 'not-allowed' : 'pointer'};
  font-size: 1rem;
  font-weight: 500;
  transition: all 0.2s ease-in-out;
  min-width: 200px;

  &:hover {
    background-color: ${props => props.$disabled ? '#bdc3c7' : '#27ae60'};
  }
`;

const DangerButton = styled.button<{ $disabled?: boolean }>`
  background-color: ${props => props.$disabled ? '#bdc3c7' : '#e74c3c'};
  color: white;
  border: none;
  padding: 1rem 1.5rem;
  border-radius: 6px;
  cursor: ${props => props.$disabled ? 'not-allowed' : 'pointer'};
  font-size: 1rem;
  font-weight: 500;
  transition: all 0.2s ease-in-out;
  min-width: 200px;

  &:hover {
    background-color: ${props => props.$disabled ? '#bdc3c7' : '#c0392b'};
  }
`;

const ButtonContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-top: 1rem;
`;

const DateRangeContainer = styled.div`
  display: flex;
  gap: 1rem;
  align-items: center;
`;

const SyncButton = styled(Button)`
  width: 100%;
  padding: 0.75rem 1.5rem;
  font-size: 1rem;
  font-weight: 500;
  min-width: 200px;
`;

interface SyncJob {
  status: string;
  message?: string;
  result?: any;
  error?: string;
  start_time?: string;
  end_time?: string;
}

export default function SynkroniseringPage() {
  const [startDate, setStartDate] = useState(format(subDays(new Date(), 7), 'yyyy-MM-dd'));
  const [endDate, setEndDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [activeJobs, setActiveJobs] = useState<Record<string, SyncJob>>({});
  const [isLoading, setIsLoading] = useState(false);
  const dispatch = useAppDispatch();

  const startSync = async (syncFunction: () => Promise<any>, jobId?: string) => {
    setIsLoading(true);
    try {
      const result = await syncFunction();
      if (result?.job_id) {
        setActiveJobs(prev => ({
          ...prev,
          [result.job_id]: { status: 'processing', start_time: new Date().toISOString() }
        }));
        pollJobStatus(result.job_id);
      }
    } catch (error) {
      console.error('Synkroniseringsfeil:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const pollJobStatus = async (jobId: string) => {
    const poll = async () => {
      try {
        const status = await api.getSyncStatus(jobId);
        setActiveJobs(prev => ({
          ...prev,
          [jobId]: status
        }));

        if (status.status === 'processing') {
          setTimeout(poll, 2000); // Poll hver 2. sekund
        } else if (status.status === 'completed') {
          console.log('[Synkronisering] Synkronisering fullført, triggerer oppdatering av aktiviteter...');
          // Trigger oppdatering av aktiviteter på alle sider ved å sende en custom event
          window.dispatchEvent(new CustomEvent('syncCompleted', { 
            detail: { jobId, status } 
          }));

          // Oppdater også aktivitetstilstanden direkte i Redux,
          // slik at aktivitetslisten er oppdatert neste gang du åpner forsiden.
          // Hent først de første 100 for rask visning (inkluderer flere nye aktiviteter)
          dispatch(fetchActivities({ forceRefresh: true, limit: 100 }));
          dispatch(fetchActivityCount());
          setTimeout(() => {
            // Hent alle resterende aktiviteter (opp til 5000)
            console.log('[Synkronisering] Henter resten av aktivitetene...');
            dispatch(fetchMoreActivities({ forceRefresh: true, limit: 5000, offset: 100 }));
          }, 1500);
        }
      } catch (error) {
        console.error('Feil ved polling av jobb-status:', error);
      }
    };
    poll();
  };

  const syncNewActivities = () => {
    startSync(() => api.syncNewActivities());
  };

  const syncSelectedPeriod = () => {
    startSync(() => api.fullSyncBody(startDate, endDate));
  };

  const syncAll = () => {
    // Synkroniser aktiviteter fra 2008, helsedata fra 2020
    const end = new Date();
    const start = new Date(2008, 0, 1); // 1. januar 2008 for aktiviteter og FIT-data
    const startStr = format(start, 'yyyy-MM-dd');
    const endStr = format(end, 'yyyy-MM-dd');
    startSync(() => api.fullSyncBody(startStr, endStr));
  };

  const syncBodyBattery = () => {
    startSync(() => api.syncBodyBatteryData(startDate, endDate));
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'completed': return 'Fullført';
      case 'failed': return 'Feilet';
      case 'processing': return 'Behandler';
      case 'queued': return 'I kø';
      default: return 'Ukjent';
    }
  };

  return (
    <Container>
      <Title>Synkronisering av Data</Title>

      {/* Cache Calculation Panel */}
      <CacheCalculationPanel />

      {/* All Sync Options in One Row */}
      <SyncSection>
        <SectionTitle>Synkronisering</SectionTitle>
        <QuickActions>
          <QuickActionButton 
            onClick={syncNewActivities}
            disabled={isLoading}
          >
            Synk nye aktiviteter
          </QuickActionButton>
          
          <QuickActionButton 
            onClick={syncSelectedPeriod}
            disabled={isLoading}
          >
            Synk valgt periode
          </QuickActionButton>
          
          <QuickActionButton 
            onClick={syncBodyBattery}
            disabled={isLoading}
          >
            Synk Body Battery
          </QuickActionButton>
          
          <DangerButton 
            onClick={syncAll}
            disabled={isLoading}
          >
            Synk alle
          </DangerButton>
        </QuickActions>
        
        {/* Date inputs for selected period */}
        <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <DateContainer style={{ marginBottom: 0 }}>
            <DateLabel>Fra dato:</DateLabel>
            <DateInput
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </DateContainer>
          <DateContainer style={{ marginBottom: 0 }}>
            <DateLabel>Til dato:</DateLabel>
            <DateInput
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </DateContainer>
        </div>
        
        <p style={{ marginTop: '1rem', fontSize: '0.9rem', color: '#7f8c8d' }}>
          ⚠️ &quot;Synk alle&quot; vil synkronisere aktiviteter og FIT-data fra 2008, helsedata fra 2020. Kan ta lang tid.
        </p>
      </SyncSection>

      {/* Active Jobs */}
      {Object.keys(activeJobs).length > 0 && (
        <SyncSection>
          <SectionTitle>Aktive Synkroniseringsjobber</SectionTitle>
          {Object.entries(activeJobs).map(([jobId, job]) => (
            <StatusContainer key={jobId}>
              <div>
                <strong>Jobb ID:</strong> {jobId.substring(0, 8)}...
              </div>
              <StatusText $status={job.status}>
                Status: {getStatusText(job.status)}
              </StatusText>
              {job.message && (
                <div style={{ marginTop: '0.5rem' }}>
                  <strong>Melding:</strong> {job.message}
                </div>
              )}
              {job.error && (
                <div style={{ marginTop: '0.5rem', color: '#e74c3c' }}>
                  <strong>Feil:</strong> {job.error}
                </div>
              )}
              {job.status === 'processing' && (
                <ProgressBar $progress={50} />
              )}
              {job.start_time && (
                <div style={{ marginTop: '0.5rem', fontSize: '0.9rem', color: '#7f8c8d' }}>
                  Startet: {format(new Date(job.start_time), 'dd.MM.yyyy HH:mm', { locale: nb })}
                </div>
              )}
              {job.end_time && (
                <div style={{ fontSize: '0.9rem', color: '#7f8c8d' }}>
                  Avsluttet: {format(new Date(job.end_time), 'dd.MM.yyyy HH:mm', { locale: nb })}
                </div>
              )}
            </StatusContainer>
          ))}
        </SyncSection>
      )}

      {/* Information */}
      <SyncSection>
        <SectionTitle>Informasjon</SectionTitle>
        <div style={{ lineHeight: '1.6' }}>
          <p><strong>Hva synkroniseres:</strong></p>
          <ul>
            <li><strong>Aktiviteter:</strong> Alle aktiviteter fra Garmin Connect med GPS-data, styrketrening, svømming, etc.</li>
            <li><strong>FIT-data:</strong> Detaljerte aktivitetsdata for løpeaktiviteter (hastighet, hjertefrekvens, kadens, etc.)</li>
            <li><strong>Helsedata:</strong> HRV-data, kroppsbatteri, og andre helsemetrics</li>
            <li><strong>Training Effect:</strong> EPOC, Training Load, og andre treningsmetrics</li>
            <li><strong>HRV Database:</strong> HRV-data synkroniseres automatisk til database for raskere tilgang</li>
          </ul>
          
          <p><strong>Hva beregnes og lagres:</strong></p>
          <ul>
            <li><strong>Power:</strong> Løpekraft for alle løpeaktiviteter (lagres i database for raskere henting)</li>
            <li><strong>Training Stress Score:</strong> TSS-beregninger for alle aktiviteter</li>
            <li><strong>Caching:</strong> Forbereder data for raskere visning på alle sider</li>
          </ul>
          
          <p><strong>Tips:</strong></p>
          <ul>
            <li><strong>&quot;Synk nye aktiviteter&quot;</strong> er den enkleste måten å holde data oppdatert - den finner automatisk siste aktivitet og synker fra den datoen</li>
            <li><strong>&quot;Synk valgt periode&quot;</strong> for å synkronisere en spesifikk tidsperiode</li>
            <li><strong>&quot;Synk alle&quot;</strong> for full synkronisering av alle aktiviteter fra 2008 og helsedata fra 2020 (kan ta lang tid)</li>
            <li>Du kan lukke denne siden - synkroniseringen fortsetter i bakgrunnen</li>
            <li>Sjekk status på jobbene nedenfor for å følge fremgangen</li>
          </ul>
        </div>
      </SyncSection>
    </Container>
  );
} 