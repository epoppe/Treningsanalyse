'use client';

import React, { useState, useEffect } from 'react';
import { activitiesApi } from '../../utils/api';

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

const getRecommendation = (status: string): string => {
  const recommendations: { [key: string]: string } = {
    optimal: 'Du er klar for intensiv trening. Gå for det!',
    good: 'Du kan gjøre moderat til intensiv trening. Lytt til kroppen.',
    moderate: 'Gjør lett til moderat trening. Fokuser på teknikk og form.',
    poor: 'Gjør lett trening eller hvile. Prioriter recovery.',
    very_poor: 'Ta en hviledag. Fokuser på søvn og recovery.',
    unknown: 'Ikke nok data til å gi anbefaling.'
  };
  return recommendations[status] || 'Ingen anbefaling tilgjengelig.';
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

  useEffect(() => {
    // Sett dagens dato som standard
    const today = new Date().toISOString().split('T')[0];
    setSelectedDate(today);
    fetchReadiness(today);
  }, []);

  const fetchReadiness = async (date: string) => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await activitiesApi.getTrainingReadiness(date);
      setReadinessData(response.data || response);
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
            <h3 className="text-xl font-semibold mb-4 text-gray-800">Daglig Readiness Score</h3>
            <div className="flex items-center gap-4 mb-4">
              <div
                className="w-15 h-15 rounded-full flex items-center justify-center text-xl font-bold text-white"
                style={{ backgroundColor: getScoreColor(readinessData.total_score) }}
              >
                {Math.round(readinessData.total_score)}
              </div>
              <div className="flex-1">
                <div className="text-2xl font-bold text-gray-800">
                  {Math.round(readinessData.total_score)}/100
                </div>
                <div className="text-sm text-gray-500 capitalize">
                  {getStatusText(readinessData.readiness_status)}
                </div>
              </div>
            </div>
            
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mt-4 text-blue-800 text-sm">
              <strong>Anbefaling:</strong> {getRecommendation(readinessData.readiness_status)}
            </div>
          </div>

          <div className="bg-white rounded-xl p-6 shadow-lg">
            <h3 className="text-xl font-semibold mb-4 text-gray-800">Komponenter</h3>
            <div className="grid grid-cols-2 gap-2 mt-4">
              {Object.entries(readinessData.components).map(([component, score]) => (
                <div key={component} className="flex justify-between p-2 bg-gray-50 rounded">
                  <span className="text-sm text-gray-700 capitalize">
                    {component.replace('_', ' ')}
                  </span>
                  <span className="text-sm font-semibold text-gray-800">
                    {Math.round(score as number)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {readinessData && (
        <div className="bg-white rounded-xl p-6 shadow-lg mt-8">
          <h3 className="text-xl font-semibold mb-4 text-gray-800">
            Dato: {formatDate(readinessData.date)}
          </h3>
          <p className="text-gray-600">
            Daglig readiness score beregnet basert på søvn, HRV, aktivitet og recovery data fra de siste 7 dagene.
          </p>
        </div>
      )}
    </div>
  );
} 