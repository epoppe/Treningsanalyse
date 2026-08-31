'use client';

import React, { useState, useEffect } from 'react';
import { activitiesApi } from '../../utils/api';
import ReadinessChat from '../../components/ReadinessChat';
import {
  getFormValueDescription,
  getReadinessRecommendation,
} from '../../components/trainingReadinessUtils';
import {
  MetricAlert,
  MetricDateField,
  MetricFilterCard,
  MetricLoading,
  MetricPageLayout,
  MetricPrimaryButton,
} from '@/components/layout/MetricPageLayout';

function readinessTone(score: number): string {
  if (score >= 60) return 'text-emerald-700';
  if (score >= 40) return 'text-amber-700';
  return 'text-red-700';
}

function readinessLabel(score: number): string {
  if (score >= 80) return 'Optimal';
  if (score >= 60) return 'God';
  if (score >= 40) return 'Moderat';
  if (score >= 20) return 'Dårlig';
  return 'Svært dårlig';
}

export default function DagligReadinessPage() {
  const [selectedDate, setSelectedDate] = useState('');
  const [readinessData, setReadinessData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
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
    } catch {
      setError('Kunne ikke hente daglig readiness-data');
    } finally {
      setLoading(false);
    }
  };

  const handleTodayClick = () => {
    const today = new Date().toISOString().split('T')[0];
    setSelectedDate(today);
    fetchReadiness(today);
  };

  return (
    <MetricPageLayout
      title="Daglig readiness"
      subtitle="Readiness-score, form og anbefaling for valgt dag"
    >
      <MetricFilterCard>
        <div className="flex flex-wrap items-end gap-3">
          <MetricDateField
            id="readiness-date"
            label="Dato"
            value={selectedDate}
            onChange={(date) => {
              setSelectedDate(date);
              fetchReadiness(date);
            }}
          />
          <MetricPrimaryButton onClick={handleTodayClick}>I dag</MetricPrimaryButton>
        </div>
      </MetricFilterCard>

      {loading ? <MetricLoading>Laster daglig readiness...</MetricLoading> : null}
      {error ? <MetricAlert>{error}</MetricAlert> : null}

      {readinessData && !loading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              Status
            </p>
            <p className={`mt-2 text-3xl font-semibold tabular-nums ${readinessTone(readinessData.total_score)}`}>
              {Math.round(readinessData.total_score)}
              <span className="text-base font-medium text-slate-500"> / 100</span>
            </p>
            <p className="mt-1 text-sm font-medium text-slate-700">
              {readinessLabel(readinessData.total_score)}
            </p>

            {readinessData.details?.form_value != null ? (
              <div className="mt-4 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                <p className="text-xs text-slate-500">Form (TSB)</p>
                <p className="text-lg font-semibold tabular-nums text-slate-900">
                  {readinessData.details.form_value.toFixed(1)}{' '}
                  <span className="text-sm font-medium text-slate-600">
                    {getFormValueDescription(readinessData.details.form_value)}
                  </span>
                </p>
              </div>
            ) : null}

            <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
              <strong className="font-semibold text-slate-900">Anbefaling:</strong>{' '}
              {getReadinessRecommendation(
                readinessData.readiness_status,
                readinessData.has_trained_on_date,
              )}
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-900">Komponenter</h3>
            <div className="mt-3 space-y-2">
              {Object.entries(readinessData.components || {}).map(([component, score]) => {
                const componentNames: Record<string, string> = {
                  sleep_score: 'Søvn (15 % vekt)',
                  hrv_score: 'HRV (15 % vekt)',
                  form_score: 'Form/TSB (70 % vekt)',
                };
                return (
                  <div
                    key={component}
                    className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2"
                  >
                    <span className="text-sm text-slate-600">
                      {componentNames[component] || component.replace(/_/g, ' ')}
                    </span>
                    <span className="text-sm font-semibold tabular-nums text-slate-900">
                      {Math.round(score as number)}
                    </span>
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      ) : null}

      {!loading ? (
        <div className="mt-2">
          <ReadinessChat
            selectedDate={selectedDate}
            onSendMessage={async (message, date) => {
              return await activitiesApi.getReadinessChatResponse(message, date);
            }}
          />
        </div>
      ) : null}
    </MetricPageLayout>
  );
}
