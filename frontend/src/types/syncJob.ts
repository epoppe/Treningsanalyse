/**
 * Svar fra GET /api/sync/status/{job_id} (backend sync.py).
 * 404 fra Axios håndteres i getSyncStatus og gir syntetisk not_found-objekt.
 */
export type SyncJobLifecycleStatus =
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'not_found';

export interface SyncMetricsCalculated {
  negative_split?: number;
  decoupling?: number;
  hrv_available?: number;
  total_activities?: number;
  tss?: number;
  power?: number;
  running_economy?: number;
}

export interface SyncSummaryPayload {
  metrics_calculated?: {
    from_sync?: SyncMetricsCalculated;
    from_fit_data?: SyncMetricsCalculated;
  };
  hrv_synced?: boolean;
  te_synced?: boolean;
  summaries_updated?: boolean;
}

export interface SyncSummaryResultPayload {
  status?: string;
  message?: string;
}

export interface SyncValidationActivityRow {
  activity_id: string;
  name?: string | null;
  date?: string | null;
  has_fit: boolean;
  has_fatigue: boolean;
  has_decoupling: boolean;
  has_hrv: boolean;
}

export interface SyncValidationReport {
  total_activities: number;
  with_fit: number;
  with_fatigue: number;
  with_decoupling: number;
  with_hrv: number;
  summary_text: string;
  activities?: SyncValidationActivityRow[];
}

export interface SyncJobProgress {
  phase: number;
  total_phases: number;
  percent: number;
  label: string;
  sub_current?: number;
  sub_total?: number;
  sub_label?: string;
}

export interface SyncJobResultPayload {
  summary?: SyncSummaryPayload;
  summary_result?: SyncSummaryResultPayload;
  validation?: SyncValidationReport;
  synced_activity_ids?: string[];
  period?: { start?: string; end?: string };
}

export interface SyncJobStatusResponse {
  job_id: string;
  status: SyncJobLifecycleStatus | string;
  job_type?: string;
  message?: string;
  progress?: SyncJobProgress | null;
  error?: string;
  created_at?: string;
  start_time?: string | null;
  end_time?: string | null;
  result?: SyncJobResultPayload;
  is_active?: boolean;
}

/** GET /api/sync/garmin-status */
export interface GarminSyncStatusResponse {
  ready: boolean;
  auth_state: 'authenticated' | 'token_cache' | 'credentials_only' | 'missing' | string;
  has_credentials: boolean;
  has_token_cache: boolean;
  email_configured: boolean;
  masked_email: string;
  token_dir: string;
  desktop_mode: boolean;
  config_env_path?: string | null;
  detail?: string | null;
}
