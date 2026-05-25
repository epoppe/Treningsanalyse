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

export interface SyncJobResultPayload {
  summary?: SyncSummaryPayload;
  summary_result?: SyncSummaryResultPayload;
}

export interface SyncJobStatusResponse {
  job_id: string;
  status: SyncJobLifecycleStatus | string;
  job_type?: string;
  message?: string;
  error?: string;
  created_at?: string;
  start_time?: string | null;
  end_time?: string | null;
  result?: SyncJobResultPayload;
  is_active?: boolean;
}
