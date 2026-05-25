/** Delte norske etiketter for bakgrunns-synkjobber (backend job_type / status). */

export const JOB_TYPE_LABELS: Record<string, string> = {
  activities_sync: 'Aktiviteter (+ FIT)',
  new_activities_sync: 'Nye aktiviteter (hel pipeline)',
  full_sync: 'Full synkronisering',
  health_sync: 'Helsedata',
  fit_download: 'FIT-nedlasting',
  training_effect_sync: 'Training Effect',
  hrv_sync: 'HRV til database',
  body_battery_sync: 'Body Battery',
  calculations: 'Beregninger / cache',
};

export function jobTypeLabel(jobType?: string): string {
  if (!jobType) return 'Synk-jobb';
  return JOB_TYPE_LABELS[jobType] ?? jobType;
}

export function syncStatusLabel(status: string): string {
  switch (status) {
    case 'completed':
      return 'Fullført';
    case 'failed':
      return 'Feilet';
    case 'processing':
      return 'Behandler';
    case 'queued':
      return 'I kø';
    case 'not_found':
      return 'Ikke funnet';
    default:
      return status || 'Ukjent';
  }
}
