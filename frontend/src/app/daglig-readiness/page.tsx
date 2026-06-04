'use client';

import React, { useState, useEffect } from 'react';
import { activitiesApi } from '../../utils/api';
import ReadinessChat from '../../components/ReadinessChat';
import {
  getFormValueDescription,
  getReadinessRecommendation,
} from '../../components/trainingReadinessUtils';

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
            
            {readinessData.details?.form_value !== undefined && readinessData.details?.form_value !== null && (
              <div className="mt-6 p-3 bg-blue-50 rounded" style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#000000' }}>
                Form: {readinessData.details.form_value.toFixed(1)}
                {' '}
                {getFormValueDescription(readinessData.details.form_value)}
              </div>
            )}
            
            <div style={{ marginTop: '2rem' }}></div>
            
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-blue-800 text-sm">
              <strong>Anbefaling:</strong> {getReadinessRecommendation(readinessData.readiness_status, readinessData.has_trained_on_date)}
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
