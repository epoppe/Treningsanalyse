'use client';

import React, { useState, useEffect } from 'react';
import { activitiesApi } from '../../utils/api';
import { useAppSelector } from '../../store/hooks';
import ReadinessChat from '../../components/ReadinessChat';

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

const getRecommendation = (status: string, hasTrainedOnDate: boolean): string => {
  const baseRecommendations: { [key: string]: string } = {
    optimal: 'Du er klar for intensiv trening. Gå for det!',
    good: 'Du kan gjøre moderat til intensiv trening. Lytt til kroppen.',
    moderate: 'Gjør lett til moderat trening. Fokuser på teknikk og form.',
    poor: 'Gjør lett trening eller hvile. Prioriter recovery.',
    very_poor: 'Ta en hviledag. Fokuser på søvn og recovery.',
    unknown: 'Ikke nok data til å gi anbefaling.'
  };
  
  const base = baseRecommendations[status] || 'Ingen anbefaling tilgjengelig.';
  
  if (hasTrainedOnDate) {
    return `Du har trent denne dagen. ${base}`;
  } else {
    return `Du har ikke trent denne dagen. ${base}`;
  }
};

const getScoreColor = (score: number): string => {
  if (score >= 80) return '#10b981'; // Grønn
  if (score >= 60) return '#3b82f6'; // Blå
  if (score >= 40) return '#f59e0b'; // Gul
  if (score >= 20) return '#ef4444'; // Rød
  return '#6b7280'; // Grå
};

export default function DagligReadinessPage() {
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [readinessData, setReadinessData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasTrainedOnDate, setHasTrainedOnDate] = useState<boolean>(false);
  const [formValue, setFormValue] = useState<number | null>(null);
  
  const activities = useAppSelector((state) => state.activities.items || []);

  useEffect(() => {
    // Sett dagens dato som standard
    const today = new Date().toISOString().split('T')[0];
    setSelectedDate(today);
    fetchReadiness(today);
  }, []);

  // Oppdater sjekk for trening når aktiviteter eller valgt dato endres
  useEffect(() => {
    const checkTrainingForDate = async () => {
      if (!selectedDate) {
        setHasTrainedOnDate(false);
        return;
      }
      
      const selectedDateStr = selectedDate; // selectedDate er allerede i YYYY-MM-DD format
      console.log('[Readiness] Sjekker aktiviteter for dato:', selectedDateStr);
      console.log('[Readiness] Totalt aktiviteter i store:', activities.length);
      
      // Sjekk først i eksisterende aktiviteter
      let hasTrained = false;
      
      if (activities.length > 0) {
        // Logg noen eksempler for debugging
        if (activities.length > 0) {
          const sampleActivity = activities[0];
          console.log('[Readiness] Eksempel aktivitet:', {
            activityId: sampleActivity.activityId,
            startTimeLocal: sampleActivity.startTimeLocal,
            parsedDate: sampleActivity.startTimeLocal ? new Date(sampleActivity.startTimeLocal).toISOString().split('T')[0] : 'N/A'
          });
        }
        
        hasTrained = activities.some(activity => {
          if (!activity.startTimeLocal) {
            return false;
          }
          
          // Konverter til dato-string for sammenligning
          try {
            const activityDate = new Date(activity.startTimeLocal);
            // Bruk lokal tid for dato-sammenligning (ikke UTC)
            // Dette håndterer timezone-problemer bedre
            const year = activityDate.getFullYear();
            const month = String(activityDate.getMonth() + 1).padStart(2, '0');
            const day = String(activityDate.getDate()).padStart(2, '0');
            const activityDateStr = `${year}-${month}-${day}`;
            
            const matches = activityDateStr === selectedDateStr;
            if (matches) {
              console.log('[Readiness] Funnet match i store! Aktivitet:', activity.activityId, 'startTimeLocal:', activity.startTimeLocal, 'Dato:', activityDateStr);
            }
            return matches;
          } catch (e) {
            console.error('[Readiness] Feil ved parsing av dato:', activity.startTimeLocal, e);
            return false;
          }
        });
      }
      
      // Hvis ikke funnet i store, hent aktiviteter for den spesifikke datoen
      if (!hasTrained) {
        try {
          console.log('[Readiness] Henter aktiviteter for dato:', selectedDateStr);
          const response = await activitiesApi.getActivitiesByDateRange(selectedDateStr, selectedDateStr, false);
          const dateActivities = response?.activities || [];
          console.log('[Readiness] Hentet', dateActivities.length, 'aktiviteter for dato:', selectedDateStr);
          
          if (dateActivities.length > 0) {
            console.log('[Readiness] Funnet aktiviteter for dato:', selectedDateStr, dateActivities);
            hasTrained = true;
          }
        } catch (err) {
          console.error('[Readiness] Feil ved henting av aktiviteter for dato:', err);
        }
      }
      
      console.log('[Readiness] Har trent på', selectedDateStr, ':', hasTrained);
      setHasTrainedOnDate(hasTrained);
    };
    
    checkTrainingForDate();
  }, [selectedDate, activities]);

  const fetchReadiness = async (date: string) => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await activitiesApi.getTrainingReadiness(date);
      setReadinessData(response.data || response);
      
      // Hent Form-verdi fra TSS API for samme dato
      // Vi må bruke samme tilnærming som TSS-siden: hent med en periode som slutter på valgt dato
      // summary.current_form vil da være Form-verdien for sluttdatoen (valgt dato)
      // For å få riktig CTL/ATL beregning, må vi starte fra 2008 (eller så langt tilbake som mulig)
      const dateObj = new Date(date);
      const startDate = new Date('2008-01-01'); // Start fra 2008 for å sikre riktig CTL/ATL beregning
      const endDate = new Date(dateObj); // Sluttdato er valgt dato
      
      try {
        const tssResponse = await fetch(
          `/api/training-stress/metrics?start_date=${startDate.toISOString().split('T')[0]}&end_date=${endDate.toISOString().split('T')[0]}`
        );
        if (tssResponse.ok) {
          const tssData = await tssResponse.json();
          console.log('TSS API response for date:', date, 'summary:', tssData.data?.summary);
          
          // Bruk summary.current_form - dette er Form-verdien for sluttdatoen (valgt dato)
          // Dette er samme verdi som TSS-siden viser når den henter data med samme end_date
          if (tssData.data?.summary?.current_form !== undefined) {
            console.log('Form-verdi funnet i summary.current_form for', date, ':', tssData.data.summary.current_form);
            setFormValue(tssData.data.summary.current_form);
          } else if (tssData.data?.daily_data && Array.isArray(tssData.data.daily_data) && tssData.data.daily_data.length > 0) {
            // Fallback: Hent fra siste dag i daily_data (som skal være sluttdatoen)
            const lastDay = tssData.data.daily_data[tssData.data.daily_data.length - 1];
            if (lastDay?.form !== undefined) {
              console.log('Form-verdi funnet fra siste dag i daily_data (fallback):', lastDay.form);
              setFormValue(lastDay.form);
            } else {
              console.warn('Ingen Form-verdi funnet i daily_data for dato:', date);
              setFormValue(null);
            }
          } else {
            console.warn('Ingen Form-verdi funnet for dato:', date);
            setFormValue(null);
          }
        } else {
          console.warn('TSS API response ikke OK:', tssResponse.status);
          setFormValue(null);
        }
      } catch (tssErr) {
        console.error('Kunne ikke hente Form-verdi fra TSS API:', tssErr);
        setFormValue(null);
      }
    } catch (err) {
      console.error('Feil ved henting av daglig readiness:', err);
      setError('Kunne ikke hente daglig readiness data');
    } finally {
      setLoading(false);
    }
  };

  const handleDateChange = (date: string) => {
    setSelectedDate(date);
    fetchReadiness(date);
  };

  const handleTodayClick = () => {
    const today = new Date().toISOString().split('T')[0];
    setSelectedDate(today);
    fetchReadiness(today);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('nb-NO', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  };

  return (
    <div className="max-w-6xl mx-auto p-8">
      <h1 className="text-4xl text-gray-800 mb-8 text-center">Daglig Training Readiness</h1>
      
      <div className="flex justify-center items-center gap-4 mb-8">
        <input
          type="date"
          value={selectedDate}
          onChange={(e) => handleDateChange(e.target.value)}
          className="px-4 py-2 border border-gray-300 rounded-md text-base"
        />
        <button
          onClick={handleTodayClick}
          className="px-4 py-2 bg-green-600 text-white border-none rounded-md cursor-pointer text-base hover:bg-green-700"
        >
          I dag
        </button>
      </div>

      {loading && (
        <div className="flex justify-center items-center h-48 text-gray-500">
          Laster daglig readiness...
        </div>
      )}

      {error && (
        <div className="text-red-500 text-center p-5">{error}</div>
      )}

      {readinessData && !loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mt-8">
          <div className="bg-white rounded-xl p-6 shadow-lg">
            <div className="mt-6 p-3 bg-blue-50 rounded" style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#000000' }}>
              Readiness Score: {Math.round(readinessData.total_score)}/100
              {' '}
              {readinessData.total_score >= 80 ? '🟢 Optimal' :
               readinessData.total_score >= 60 ? '🟢 God' :
               readinessData.total_score >= 40 ? '🟡 Moderat' :
               readinessData.total_score >= 20 ? '🔴 Dårlig' :
               '🔴 Svært dårlig'}
            </div>
            
            {formValue !== null && (
              <div className="mt-6 p-3 bg-blue-50 rounded" style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#000000' }}>
                Form: {formValue.toFixed(1)}
                {' '}
                {formValue < -15 ? '🔴 Høy fysisk fatigue' :
                 formValue < -5 ? '🟡 Moderat fysisk fatigue' :
                 formValue < 5 ? '🟢 Balansert' :
                 formValue < 15 ? '🟢 Godt restituert' :
                 '🟢 Meget frisk'}
              </div>
            )}
            
            <div style={{ marginTop: '2rem' }}></div>
            
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-blue-800 text-sm">
              <strong>Anbefaling:</strong> {getRecommendation(readinessData.readiness_status, hasTrainedOnDate)}
            </div>
          </div>

          <div className="bg-white rounded-xl p-6 shadow-lg">
            <h3 className="text-xl font-semibold mb-4 text-gray-800">Komponenter</h3>
            <div className="grid grid-cols-1 gap-2 mt-4">
              {Object.entries(readinessData.components).map(([component, score]) => {
                const componentNames: {[key: string]: string} = {
                  'sleep_score': 'Søvn (15% vekt)',
                  'hrv_score': 'HRV (15% vekt)',
                  'form_score': 'Form/TSB (70% vekt)'
                };
                return (
                  <div key={component} className="flex justify-between p-2 bg-gray-50 rounded">
                    <span className="text-sm text-gray-700">
                      {componentNames[component] || component.replace('_', ' ')}
                    </span>
                    <span className="text-sm font-semibold text-gray-800">
                      {Math.round(score as number)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {!loading && (
        <div className="mt-8">
          <ReadinessChat
            selectedDate={selectedDate}
            onSendMessage={async (message, date) => {
              return await activitiesApi.getReadinessChatResponse(message, date);
            }}
          />
        </div>
      )}

    </div>
  );
} 