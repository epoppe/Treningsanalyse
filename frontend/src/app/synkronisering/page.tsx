'use client';

import { useState, useRef, useEffect } from 'react';
import styled, { keyframes } from 'styled-components';
import { format, subDays } from 'date-fns';
import { nb } from 'date-fns/locale';
import { api } from '../../utils/api';
import CacheCalculationPanel from '../../components/CacheCalculationPanel';
import { useAppDispatch } from '@/store/hooks';
import { jobTypeLabel, syncStatusLabel } from '@/utils/syncJobLabels';
import type { SyncJobStatusResponse } from '@/types/syncJob';
import { messageFromApiError } from '@/utils/httpErrorMessage';
import { refreshActivitiesAfterSync } from '@/utils/syncRefresh';

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

const DeterminateProgress = styled.div<{ $percent: number }>`
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
    width: ${(p) => `${Math.min(100, Math.max(0, p.$percent))}%`};
    background: linear-gradient(90deg, #3498db, #2980b9);
    transition: width 0.4s ease;
  }
`;

const ValidationBox = styled.div`
  margin-top: 0.75rem;
  padding: 0.75rem;
  background: #eef9f0;
  border: 1px solid #b8dfc4;
  border-radius: 4px;
  font-size: 0.9rem;
  color: #1e5631;
`;

/** Ubestemt fremdrift når prosent ikke er tilgjengelig */
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

const PrimaryButton = styled(QuickActionButton)`
  min-width: 260px;
  font-size: 1.05rem;
  padding: 1.1rem 1.75rem;
`;

const SecondaryButton = styled.button<{ $disabled?: boolean }>`
  background-color: ${props => props.$disabled ? '#bdc3c7' : '#3498db'};
  color: white;
  border: none;
  padding: 0.85rem 1.25rem;
  border-radius: 6px;
  cursor: ${props => props.$disabled ? 'not-allowed' : 'pointer'};
  font-size: 0.95rem;
  font-weight: 500;
  transition: all 0.2s ease-in-out;

  &:hover {
    background-color: ${props => props.$disabled ? '#bdc3c7' : '#2980b9'};
  }
`;

const ActionGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  margin-bottom: 1.5rem;
`;

const ActionBlock = styled.div`
  padding: 1.25rem;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fafbfc;
`;

const ActionBlockTitle = styled.h3`
  margin: 0 0 0.35rem;
  font-size: 1.05rem;
  color: #2c3e50;
`;

const ActionBlockText = styled.p`
  margin: 0 0 1rem;
  color: #566573;
  font-size: 0.92rem;
  line-height: 1.5;
  max-width: 42rem;
`;

const ActionRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: flex-end;
`;

const DateFields = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 1rem;
`;

const AdvancedDetails = styled.details`
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  background: #fff;

  summary {
    cursor: pointer;
    font-weight: 600;
    color: #34495e;
    list-style: none;
  }

  summary::-webkit-details-marker {
    display: none;
  }

  &[open] summary {
    margin-bottom: 0.75rem;
  }
`;

const HintText = styled.p`
  margin: 0.5rem 0 0;
  font-size: 0.88rem;
  color: #7f8c8d;
  line-height: 1.45;
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

  const pollJobStatus = (jobId: string) => {
    let consecutiveErrors = 0;
    const MAX_POLL_ERRORS = 15;

    const poll = async () => {
      try {
        const status = await api.getSyncStatus(jobId);
        consecutiveErrors = 0;
        setActiveJobs(prev => ({
          ...prev,
          [jobId]: {
            ...prev[jobId],
            ...status,
            job_id: status.job_id ?? jobId,
          },
        }));

        const stillActive =
          status.is_active === true
          || status.status === 'processing'
          || status.status === 'queued';

        if (stillActive) {
          setTimeout(poll, 2000);
          return;
        }

        if (status.status === 'completed') {
          console.log('[Synkronisering] Synkronisering fullført, triggerer oppdatering av aktiviteter...');
          window.dispatchEvent(new CustomEvent('syncCompleted', {
            detail: { jobId, status },
          }));

          refreshActivitiesAfterSync(dispatch, status);
          scheduleRemoveJobFromList(jobId, REMOVE_JOB_AFTER_MS.completed);
        } else if (status.status === 'failed') {
          scheduleRemoveJobFromList(jobId, REMOVE_JOB_AFTER_MS.failed);
        } else if (status.status === 'not_found') {
          scheduleRemoveJobFromList(jobId, REMOVE_JOB_AFTER_MS.not_found);
        } else {
          console.warn('[Synkronisering] Uventet jobbstatus, fortsetter polling:', status.status);
          setTimeout(poll, 3000);
        }
      } catch (error) {
        consecutiveErrors += 1;
        console.error('Feil ved polling av jobb-status:', error);
        if (consecutiveErrors < MAX_POLL_ERRORS) {
          setTimeout(poll, 3000);
          return;
        }
        setActiveJobs(prev => ({
          ...prev,
          [jobId]: {
            ...prev[jobId],
            job_id: jobId,
            status: 'failed',
            error: 'Kunne ikke hente jobbstatus fra server. Sjekk at backend kjører.',
          },
        }));
        scheduleRemoveJobFromList(jobId, REMOVE_JOB_AFTER_MS.failed);
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

  const syncFullPeriod = () => {
    const rangeErr = validateDateRange(startDate, endDate);
    if (rangeErr) {
      setSyncActionError(rangeErr);
      return;
    }
    startSync(() => api.fullSyncForPeriod(startDate, endDate));
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

  const syncGarminPerformance = () => {
    startSync(() => api.syncGarminPerformanceRecent());
  };

  return (
    <Container>
      <Title>Synkronisering av Data</Title>

      {/* Cache Calculation Panel */}
      <CacheCalculationPanel />

      <SyncSection>
        <SectionTitle>Synkronisering</SectionTitle>
        {syncActionError && (
          <ErrorBanner role="alert">{syncActionError}</ErrorBanner>
        )}

        <ActionGroup>
          <ActionBlock>
            <ActionBlockTitle>Daglig oppdatering</ActionBlockTitle>
            <ActionBlockText>
              Henter nye økter og oppdaterer alt du trenger i daglig bruk: aktiviteter, FIT, helse,
              trenings effekt, Garmin performance (VO2 max), HRV og beregninger.
            </ActionBlockText>
            <PrimaryButton onClick={syncNewActivities} disabled={isLoading}>
              Synk nye (anbefalt)
            </PrimaryButton>
          </ActionBlock>

          <ActionBlock>
            <ActionBlockTitle>Valgt periode</ActionBlockTitle>
            <ActionBlockText>
              Bruk datofeltene under for et bestemt intervall. «Kun aktiviteter» er raskest;
              «Full synk» tar med helse, TE, performance metrics og beregninger for perioden.
            </ActionBlockText>
            <DateFields>
              <DateContainer style={{ marginBottom: 0 }}>
                <DateLabel>Fra dato</DateLabel>
                <DateInput
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                />
              </DateContainer>
              <DateContainer style={{ marginBottom: 0 }}>
                <DateLabel>Til dato</DateLabel>
                <DateInput
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                />
              </DateContainer>
            </DateFields>
            <ActionRow>
              <SecondaryButton onClick={syncSelectedPeriod} disabled={isLoading}>
                Kun aktiviteter + FIT
              </SecondaryButton>
              <SecondaryButton onClick={syncFullPeriod} disabled={isLoading}>
                Full synk for perioden
              </SecondaryButton>
            </ActionRow>
          </ActionBlock>

          <AdvancedDetails>
            <summary>Avansert — reparer eller fyll inn manglende data</summary>
            <ActionBlockText>
              Disse jobbene er vanligvis ikke nødvendige hvis du bruker «Synk nye» regelmessig.
              Bruk dem ved manglende VO2 max-desimaler, trenings effekt eller Body Battery.
            </ActionBlockText>
            <ActionRow>
              <SecondaryButton onClick={refreshTrainingEffect} disabled={isLoading}>
                Hent manglende trenings effekt
              </SecondaryButton>
              <SecondaryButton onClick={syncGarminPerformance} disabled={isLoading}>
                Synk Garmin performance (90 dager)
              </SecondaryButton>
              <SecondaryButton onClick={syncBodyBattery} disabled={isLoading}>
                Synk Body Battery for perioden
              </SecondaryButton>
            </ActionRow>
          </AdvancedDetails>

          <ActionBlock>
            <ActionBlockTitle>Full historikk</ActionBlockTitle>
            <ActionBlockText>
              Bred synkronisering fra 2008 (aktivitet/FIT) og 2020 (helse) til i dag.
              Kan ta lang tid — bruk bare ved første gangs oppsett eller større hull i data.
            </ActionBlockText>
            <DangerButton onClick={syncAll} disabled={isLoading}>
              Full historikk-synk
            </DangerButton>
            <HintText>
              Forvent lang kjøretid. Lukk gjerne siden — jobben kjører på serveren.
            </HintText>
          </ActionBlock>
        </ActionGroup>
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
              {job.progress && (job.status === 'processing' || job.status === 'queued') && (
                <div style={{ marginTop: '0.5rem', fontSize: '0.9rem', color: '#566573' }}>
                  Steg {job.progress.phase}/{job.progress.total_phases}
                  {job.progress.sub_label ? ` · ${job.progress.sub_label}` : ''}
                  {' · '}{job.progress.percent}%
                </div>
              )}
              {job.progress && (job.status === 'processing' || job.status === 'queued') ? (
                <DeterminateProgress $percent={job.progress.percent} aria-label="Synk-fremdrift" />
              ) : (job.status === 'processing' || job.status === 'queued') ? (
                <IndeterminateProgress aria-label="Jobb kjører" />
              ) : null}
              {job.status === 'completed' && job.result?.validation && (
                <ValidationBox>
                  <strong>Kvalitetssjekk:</strong> {job.result.validation.summary_text}
                </ValidationBox>
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
          <p><strong>Anbefalt rutine:</strong> Bruk <strong>Synk nye (anbefalt)</strong> etter trening eller én gang om dagen.</p>
          <p><strong>Valgt periode:</strong> «Kun aktiviteter + FIT» er rask re-import av økter. «Full synk for perioden» inkluderer også helse, TE, VO2 max og beregninger.</p>
          <p><strong>Avansert:</strong> Reparasjonsjobber for når enkeltfelter mangler uten at du trenger full historikk-synk.</p>
          <p><strong>Jobbstatus:</strong> Du kan lukke siden mens jobben kjører. Fullførte jobber forsvinner etter noen sekunder; feilede vises lenger.</p>
        </div>
      </SyncSection>
    </Container>
  );
} 