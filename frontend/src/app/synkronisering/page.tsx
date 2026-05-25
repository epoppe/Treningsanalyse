'use client';

import { useState, useRef, useEffect } from 'react';
import styled, { keyframes } from 'styled-components';
import { format, subDays } from 'date-fns';
import { nb } from 'date-fns/locale';
import { api } from '../../utils/api';
import CacheCalculationPanel from '../../components/CacheCalculationPanel';
import { useAppDispatch } from '@/store/hooks';
import { fetchActivities, fetchMoreActivities, fetchActivityCount } from '@/store/slices/activitiesSlice';
import { jobTypeLabel, syncStatusLabel } from '@/utils/syncJobLabels';
import type { SyncJobStatusResponse } from '@/types/syncJob';
import { messageFromApiError } from '@/utils/httpErrorMessage';

/** Fjerner jobbkort fra listen etter terminaltilstand (lesbar tid for feilmeldinger). */
const REMOVE_JOB_AFTER_MS = {
  completed: 14_000,
  failed: 48_000,
  not_found: 8_000,
} as const;

function parseLocalYmd(ymd: string): Date {
  const [y, m, d] = ymd.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function validateDateRange(start: string, end: string): string | null {
  if (!start?.trim() || !end?.trim()) return 'Velg både fra- og til-dato.';
  if (parseLocalYmd(start) > parseLocalYmd(end)) return 'Fra-dato kan ikke være etter til-dato.';
  return null;
}

const ErrorBanner = styled.div`
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
  border-radius: 6px;
  background: #fdecea;
  border: 1px solid #f5c6cb;
  color: #721c24;
  font-size: 0.95rem;
`;

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
      case 'queued': return '#e67e22';
      default: return '#7f8c8d';
    }
  }};
  font-weight: 500;
`;

const indeterminateMove = keyframes`
  0% {
    transform: translateX(-120%);
  }
  100% {
    transform: translateX(320%);
  }
`;

/** Ubestemt fremdrift (ingen falsk prosent) */
const IndeterminateProgress = styled.div`
  width: 100%;
  height: 8px;
  background-color: #ecf0f1;
  border-radius: 4px;
  overflow: hidden;
  margin-top: 0.5rem;
  position: relative;

  &::after {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 35%;
    background: linear-gradient(90deg, transparent, #3498db 40%, #2980b9 60%, transparent);
    animation: ${indeterminateMove} 1.4s ease-in-out infinite;
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

export default function SynkroniseringPage() {
  const [startDate, setStartDate] = useState(format(subDays(new Date(), 7), 'yyyy-MM-dd'));
  const [endDate, setEndDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [activeJobs, setActiveJobs] = useState<Record<string, SyncJobStatusResponse>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [syncActionError, setSyncActionError] = useState<string | null>(null);
  const dispatch = useAppDispatch();
  const removeJobTimeoutsRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => () => {
    removeJobTimeoutsRef.current.forEach(clearTimeout);
    removeJobTimeoutsRef.current.clear();
  }, []);

  const scheduleRemoveJobFromList = (id: string, delayMs: number) => {
    const prev = removeJobTimeoutsRef.current.get(id);
    if (prev) clearTimeout(prev);
    const t = setTimeout(() => {
      removeJobTimeoutsRef.current.delete(id);
      setActiveJobs(jobs => {
        if (!(id in jobs)) return jobs;
        const next = { ...jobs };
        delete next[id];
        return next;
      });
    }, delayMs);
    removeJobTimeoutsRef.current.set(id, t);
  };

  const startSync = async (syncFunction: () => Promise<any>) => {
    setSyncActionError(null);
    setIsLoading(true);
    try {
      const result = await syncFunction();
      if (result?.job_id) {
        const initialStatus =
          result.status === 'queued' || result.status === 'processing' ? result.status : 'processing';
        setActiveJobs(prev => ({
          ...prev,
          [result.job_id]: {
            status: initialStatus,
            start_time: new Date().toISOString(),
            job_type: result.job_type,
            job_id: result.job_id,
            message: typeof result.message === 'string' ? result.message : undefined,
          },
        }));
        pollJobStatus(result.job_id);
      } else {
        setSyncActionError(
          typeof result?.message === 'string'
            ? result.message
            : 'Server returnerte ikke jobb-id. Sjekk at backend kjører og prøv igjen.',
        );
      }
    } catch (error) {
      console.error('Synkroniseringsfeil:', error);
      setSyncActionError(messageFromApiError(error));
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
          [jobId]: {
            ...prev[jobId],
            ...status,
            job_id: status.job_id ?? jobId,
          },
        }));

        if (status.status === 'processing' || status.status === 'queued') {
          setTimeout(poll, 2000); // Poll hver 2. sekund
        } else if (status.status === 'completed') {
          console.log('[Synkronisering] Synkronisering fullført, triggerer oppdatering av aktiviteter...');
          window.dispatchEvent(new CustomEvent('syncCompleted', {
            detail: { jobId, status },
          }));

          dispatch(fetchActivities({ forceRefresh: true, limit: 100 }));
          dispatch(fetchActivityCount());
          setTimeout(() => {
            console.log('[Synkronisering] Henter resten av aktivitetene...');
            dispatch(fetchMoreActivities({ forceRefresh: true, limit: 5000, offset: 100 }));
          }, 1500);
          scheduleRemoveJobFromList(jobId, REMOVE_JOB_AFTER_MS.completed);
        } else if (status.status === 'failed') {
          scheduleRemoveJobFromList(jobId, REMOVE_JOB_AFTER_MS.failed);
        } else if (status.status === 'not_found') {
          scheduleRemoveJobFromList(jobId, REMOVE_JOB_AFTER_MS.not_found);
        } else {
          console.warn('[Synkronisering] Uventet jobbstatus, stopper polling:', status.status);
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
    const rangeErr = validateDateRange(startDate, endDate);
    if (rangeErr) {
      setSyncActionError(rangeErr);
      return;
    }
    startSync(() => api.syncActivitiesForPeriod(startDate, endDate));
  };

  const syncAll = () => {
    // Full synk: aktiviteter fra 2008, helsedata fra 2020 (håndteres i backend)
    const end = new Date();
    const start = new Date(2008, 0, 1);
    const startStr = format(start, 'yyyy-MM-dd');
    const endStr = format(end, 'yyyy-MM-dd');
    startSync(() => api.fullSyncForPeriod(startStr, endStr));
  };

  const syncBodyBattery = () => {
    const rangeErr = validateDateRange(startDate, endDate);
    if (rangeErr) {
      setSyncActionError(rangeErr);
      return;
    }
    startSync(() => api.syncBodyBatteryData(startDate, endDate));
  };

  const refreshTrainingEffect = () => {
    startSync(() => api.refreshTrainingEffect(false));
  };

  return (
    <Container>
      <Title>Synkronisering av Data</Title>

      {/* Cache Calculation Panel */}
      <CacheCalculationPanel />

      {/* All Sync Options in One Row */}
      <SyncSection>
        <SectionTitle>Synkronisering</SectionTitle>
        {syncActionError && (
          <ErrorBanner role="alert">{syncActionError}</ErrorBanner>
        )}
        <p style={{ marginBottom: '1rem', color: '#566573', maxWidth: '52rem' }}>
          Velg datointervall under for handlinger som gjelder en periode. «Aktiviteter for periode» henter kun treningsøkter
          og FIT fra Garmin for intervallet — raskere enn full synk. «Full synkronisering» oppdaterer også helse, TE, HRV,
          Body Battery og kjører beregninger for perioden.
        </p>
        <QuickActions>
          <QuickActionButton 
            onClick={syncNewActivities}
            disabled={isLoading}
          >
            Synk nye (fra siste økt)
          </QuickActionButton>
          
          <QuickActionButton 
            onClick={syncSelectedPeriod}
            disabled={isLoading}
          >
            Aktiviteter for periode
          </QuickActionButton>
          
          <QuickActionButton 
            onClick={syncBodyBattery}
            disabled={isLoading}
          >
            Synk Body Battery
          </QuickActionButton>

          <QuickActionButton 
            onClick={refreshTrainingEffect}
            disabled={isLoading}
          >
            Hent aerob/anaerob effekt
          </QuickActionButton>
          
          <DangerButton 
            onClick={syncAll}
            disabled={isLoading}
          >
            Full synkronisering (bred historikk)
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
          ⚠️ «Full synkronisering» bruker aktiviteter/FIT fra 2008 til i dag; helse-relaterte data begrenses internt til 2020→
          (som i backend). Forvent lang kjøretid.
        </p>
      </SyncSection>

      {/* Active Jobs */}
      {Object.keys(activeJobs).length > 0 && (
        <SyncSection>
          <SectionTitle>Aktive Synkroniseringsjobber</SectionTitle>
          {Object.entries(activeJobs).map(([jobId, job]) => (
            <StatusContainer key={jobId}>
              <div style={{ marginBottom: '0.35rem' }}>
                <strong>Type:</strong> {jobTypeLabel(job.job_type)}
              </div>
              <div>
                <strong>Jobb ID:</strong> {jobId.substring(0, 8)}...
              </div>
              <StatusText $status={job.status}>
                Status: {syncStatusLabel(job.status)}
              </StatusText>
              {job.message && (
                <div style={{ marginTop: '0.5rem' }}>
                  <strong>Fase / melding:</strong> {job.message}
                </div>
              )}
              {job.error && (
                <div style={{ marginTop: '0.5rem', color: '#e74c3c' }}>
                  <strong>Feil:</strong> {job.error}
                </div>
              )}
              {(job.status === 'processing' || job.status === 'queued') && (
                <IndeterminateProgress aria-label="Jobb kjører" />
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
            <li><strong>«Synk nye (fra siste økt)»</strong> finner siste lagrede aktivitet og oppdaterer derfra til nå — inkluderer aktivitet, FIT, helse og TE (tilsvarende en «hent alt nytt»-jobb)</li>
            <li><strong>«Aktiviteter for periode»</strong> er for et valgt datointervall: kun aktiviteter og FIT (raskere enn full synk)</li>
            <li><strong>«Full synkronisering (bred historikk)»</strong> kjører full pipeline for en lang periode (aktivitet fra 2008, helse fra 2020 internt) — bruk med omtanke</li>
            <li>Du kan lukke denne siden — jobben kjører på serveren; status vises helt til den er ferdig i denne økten</li>
            <li>Under «Fase / melding» vises serverens nåværende steg (ikke en nøyaktig prosent)</li>
            <li>Fullførte jobber forsvinner fra listen etter noen sekunder; feilede jobber vises lenger slik at du rekker å lese feilen</li>
          </ul>
        </div>
      </SyncSection>
    </Container>
  );
} 