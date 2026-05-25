'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import styled from 'styled-components';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import PlotlyChart from '../../components/PlotlyChart';
import {
  analyticsApi,
  CriticalSpeedPaceByYearResponse,
  CriticalSpeedResponse,
  DecouplingTrendItem,
  DurationCurveMetric,
  DurationCurveResponse,
  DurationCurveScope,
  DurationCurveYearComparisonResponse,
  EfficiencyTrendItem,
  FatigueResistanceItem,
} from '../../utils/api';

const PageContainer = styled.div`
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
`;

const Title = styled.h1`
  color: #2c3e50;
  margin-bottom: 0.5rem;
`;

const Subtitle = styled.p`
  color: #666;
  margin-bottom: 1.5rem;
`;

const Controls = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
`;

const FilterButton = styled.button<{ $active?: boolean }>`
  padding: 0.45rem 1rem;
  border: 1px solid ${(props) => (props.$active ? '#3498db' : '#bdc3c7')};
  background: ${(props) => (props.$active ? '#3498db' : 'white')};
  color: ${(props) => (props.$active ? 'white' : '#2c3e50')};
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;

  &:hover {
    border-color: #3498db;
  }
`;

const Section = styled.section`
  margin-bottom: 2rem;
`;

const Card = styled.div`
  background: white;
  padding: 1.25rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
`;

const SectionTitle = styled.h2`
  color: #2c3e50;
  font-size: 1.2rem;
  margin: 0 0 1rem;
  border-bottom: 2px solid #3498db;
  padding-bottom: 0.4rem;
`;

const Grid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
`;

const MetricLabel = styled.div`
  color: #666;
  font-size: 0.85rem;
`;

const MetricValue = styled.div`
  color: #2c3e50;
  font-size: 1.35rem;
  font-weight: 700;
`;

const EmptyState = styled.div`
  color: #888;
  font-size: 0.9rem;
  padding: 0.75rem 0;
`;

const ErrorBox = styled.div`
  background: #fff3f3;
  color: #a33;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  margin-bottom: 1rem;
  font-size: 0.9rem;
`;

const TableWrap = styled.div`
  overflow-x: auto;
`;

const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;

  th,
  td {
    padding: 0.6rem 0.75rem;
    text-align: left;
    border-bottom: 1px solid #eee;
    white-space: nowrap;
  }

  th {
    color: #666;
    text-transform: uppercase;
    font-size: 0.75rem;
  }

  tbody tr:hover {
    background: #f9f9f9;
  }
`;

const Badge = styled.span<{ $tone?: 'good' | 'warn' | 'bad' | 'neutral' }>`
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  margin: 0.1rem 0.2rem 0.1rem 0;
  background: ${(props) => {
    if (props.$tone === 'good') return '#d1fae5';
    if (props.$tone === 'warn') return '#fef3c7';
    if (props.$tone === 'bad') return '#fee2e2';
    return '#e5e7eb';
  }};
  color: ${(props) => {
    if (props.$tone === 'good') return '#065f46';
    if (props.$tone === 'warn') return '#92400e';
    if (props.$tone === 'bad') return '#991b1b';
    return '#374151';
  }};
`;

const ChartBox = styled.div`
  min-height: 320px;
  overflow: visible;
`;

const LoadingText = styled.div`
  color: #666;
  padding: 2rem 0;
`;

const SmallMeta = styled.div`
  color: #888;
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
`;

type PeriodKey = '90' | '180' | '365' | 'all';

const PERIOD_DAYS: Record<PeriodKey, number | undefined> = {
  '90': 90,
  '180': 180,
  '365': 365,
  all: undefined,
};

const DURATION_CURVE_SECONDS = [30, 60, 180, 300, 600, 1200, 2400, 3600] as const;
/** Varigheter som brukes i Critical Speed-modellen (3–30 min). */
const CRITICAL_SPEED_TABLE_DURATIONS = [180, 360, 720, 1200, 1800, 3600] as const;
const CRITICAL_SPEED_TABLE_YEARS = [2024, 2025, 2026] as const;
const PACE_AXIS_STEP_SEC = 30;
const YEAR_LINE_COLORS = ['#c0392b', '#2980b9', '#27ae60', '#8e44ad', '#d35400'];

type ActivityFlag =
  | 'good_aerobic_stability'
  | 'high_drift'
  | 'possible_fatigue'
  | 'possible_hr_error'
  | 'unsuitable_for_decoupling';

const FLAG_META: Record<ActivityFlag, { label: string; tone: 'good' | 'warn' | 'bad' | 'neutral' }> = {
  good_aerobic_stability: { label: 'God aerob stabilitet', tone: 'good' },
  high_drift: { label: 'Høy drift', tone: 'bad' },
  possible_fatigue: { label: 'Mulig utmattelse', tone: 'warn' },
  possible_hr_error: { label: 'Mulig pulsfeil', tone: 'warn' },
  unsuitable_for_decoupling: { label: 'Ikke egnet for decoupling', tone: 'neutral' },
};

const DECOUPLING_REASON_LABELS: Record<string, string> = {
  too_short: 'For kort',
  interval_like_pace: 'Intervall-lignende fart',
  too_many_stops: 'For mange stopp',
  missing_heart_rate: 'Manglende puls',
  very_hilly: 'Svært kupert',
  insufficient_samples: 'For få samples',
};

interface MergedActivityRow {
  activityId: string;
  activityName?: string | null;
  startTimeLocal: string;
  distance?: number | null;
  duration?: number | null;
  avgEfficiencyFactor?: number | null;
  steadyStateEfficiencyFactor?: number | null;
  efficiencyDataQuality?: number | null;
  decouplingPercent?: number | null;
  decouplingSuitabilityFlag?: string | null;
  decouplingReasonIfUnsuitable?: string | null;
  fatigueResistanceScore?: number | null;
  paceDropPct?: number | null;
  hrDriftPct?: number | null;
  flags: ActivityFlag[];
}

const formatPaceFromSecPerKm = (secPerKm?: number | null) => {
  if (secPerKm == null || !Number.isFinite(secPerKm) || secPerKm <= 0) return '—';
  const minutes = Math.floor(secPerKm / 60);
  const seconds = Math.round(secPerKm % 60);
  return `${minutes}:${seconds.toString().padStart(2, '0')}/km`;
};

const formatPaceFromMps = (mps?: number | null) => {
  if (mps == null || !Number.isFinite(mps) || mps <= 0) return '—';
  return formatPaceFromSecPerKm(1000 / mps);
};

const formatDate = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('nb-NO');
};

const formatDurationMin = (seconds?: number | null) => {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  return `${Math.round(seconds / 60)} min`;
};

const formatDistanceKm = (meters?: number | null) => {
  if (meters == null || !Number.isFinite(meters)) return '—';
  return `${(meters / 1000).toFixed(1)} km`;
};

const formatPercent = (value?: number | null, digits = 1) => {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value.toFixed(digits)}%`;
};

const formatNumber = (value?: number | null, digits = 2) => {
  if (value == null || !Number.isFinite(value)) return '—';
  return value.toFixed(digits);
};

const formatDurationLabel = (seconds: number) => {
  if (seconds < 60) return `${seconds}s`;
  if (seconds === 3600) return '60 min';
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} t`;
};

/** Y-akse i sek/km med jevne pace-trinn; raskere pace (lavere tall) øverst. */
const buildPaceYAxisConfig = (paceSecValues: number[]) => {
  const valid = paceSecValues.filter((v) => Number.isFinite(v) && v > 0);
  if (valid.length === 0) {
    const ticks = [180, 210, 240, 270, 300, 330, 360, 390, 420, 450, 480, 540, 600];
    return { domain: [180, 600] as [number, number], ticks };
  }

  const padding = 15;
  const rawMin = Math.min(...valid);
  const rawMax = Math.max(...valid);
  let tickMin = Math.floor((rawMin - padding) / PACE_AXIS_STEP_SEC) * PACE_AXIS_STEP_SEC;
  let tickMax = Math.ceil((rawMax + padding) / PACE_AXIS_STEP_SEC) * PACE_AXIS_STEP_SEC;
  tickMin = Math.max(120, tickMin);
  tickMax = Math.min(900, tickMax);

  const ticks: number[] = [];
  for (let t = tickMin; t <= tickMax; t += PACE_AXIS_STEP_SEC) {
    ticks.push(t);
  }
  if (ticks.length < 2) {
    ticks.push(tickMin, tickMax);
  }
  return { domain: [tickMin, tickMax] as [number, number], ticks };
};

const translateDecouplingReasons = (reasons?: string | null) => {
  if (!reasons) return '—';
  return reasons
    .split(',')
    .map((part) => DECOUPLING_REASON_LABELS[part.trim()] ?? part.trim())
    .join(', ');
};

const deriveActivityFlags = (row: Omit<MergedActivityRow, 'flags'>): ActivityFlag[] => {
  const flags: ActivityFlag[] = [];

  if (row.decouplingSuitabilityFlag === 'unsuitable') {
    flags.push('unsuitable_for_decoupling');
  }

  if (row.decouplingPercent != null && row.decouplingSuitabilityFlag === 'suitable') {
    if (row.decouplingPercent <= 5) {
      flags.push('good_aerobic_stability');
    } else if (row.decouplingPercent > 10) {
      flags.push('high_drift');
    }
  }

  if (row.efficiencyDataQuality != null && row.efficiencyDataQuality < 50) {
    flags.push('possible_hr_error');
  }
  if (row.decouplingReasonIfUnsuitable?.includes('missing_heart_rate')) {
    flags.push('possible_hr_error');
  }

  if (
    (row.fatigueResistanceScore != null && row.fatigueResistanceScore < 60)
    || (row.paceDropPct != null && row.paceDropPct > 5)
  ) {
    flags.push('possible_fatigue');
  }

  return flags;
};

const mergeActivityRows = (
  efficiency: EfficiencyTrendItem[],
  decoupling: DecouplingTrendItem[],
  fatigue: FatigueResistanceItem[],
): MergedActivityRow[] => {
  const byId = new Map<string, Omit<MergedActivityRow, 'flags'>>();

  efficiency.forEach((item) => {
    byId.set(item.activityId, {
      activityId: item.activityId,
      activityName: item.activityName,
      startTimeLocal: item.startTimeLocal,
      distance: item.distance,
      duration: item.duration,
      avgEfficiencyFactor: item.avgEfficiencyFactor,
      steadyStateEfficiencyFactor: item.steadyStateEfficiencyFactor,
      efficiencyDataQuality: item.efficiencyDataQuality,
    });
  });

  decoupling.forEach((item) => {
    const existing = byId.get(item.activityId) ?? {
      activityId: item.activityId,
      activityName: item.activityName,
      startTimeLocal: item.startTimeLocal,
    };
    byId.set(item.activityId, {
      ...existing,
      activityName: existing.activityName ?? item.activityName,
      startTimeLocal: existing.startTimeLocal || item.startTimeLocal,
      distance: existing.distance ?? item.distance,
      duration: existing.duration ?? item.duration,
      avgEfficiencyFactor: existing.avgEfficiencyFactor ?? item.avgEfficiencyFactor,
      decouplingPercent: item.decouplingPercent,
      decouplingSuitabilityFlag: item.decouplingSuitabilityFlag,
      decouplingReasonIfUnsuitable: item.decouplingReasonIfUnsuitable,
    });
  });

  fatigue.forEach((item) => {
    const existing = byId.get(item.activityId) ?? {
      activityId: item.activityId,
      activityName: item.activityName,
      startTimeLocal: item.startTimeLocal,
    };
    byId.set(item.activityId, {
      ...existing,
      activityName: existing.activityName ?? item.activityName,
      startTimeLocal: existing.startTimeLocal || item.startTimeLocal,
      distance: existing.distance ?? item.distance,
      duration: existing.duration ?? item.duration,
      fatigueResistanceScore: item.fatigueResistanceScore,
      paceDropPct: item.paceDropPct,
      hrDriftPct: item.hrDriftPct,
    });
  });

  return Array.from(byId.values())
    .map((row) => ({ ...row, flags: deriveActivityFlags(row) }))
    .sort((a, b) => new Date(b.startTimeLocal).getTime() - new Date(a.startTimeLocal).getTime());
};

const modelQualityLabel = (quality?: string | null) => {
  switch (quality) {
    case 'good':
      return 'God';
    case 'fair':
      return 'Middels';
    case 'low':
      return 'Lav';
    case 'insufficient_data':
      return 'Utilstrekkelig data';
    default:
      return quality ?? '—';
  }
};

export default function AnalyticsPage() {
  const [period, setPeriod] = useState<PeriodKey>('365');
  const [curveScope, setCurveScope] = useState<DurationCurveScope>('all_time');
  const [includeTreadmill, setIncludeTreadmill] = useState(false);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);

  const [efficiency, setEfficiency] = useState<EfficiencyTrendItem[]>([]);
  const [decoupling, setDecoupling] = useState<DecouplingTrendItem[]>([]);
  const [fatigue, setFatigue] = useState<FatigueResistanceItem[]>([]);
  const [criticalSpeed, setCriticalSpeed] = useState<CriticalSpeedResponse | null>(null);
  const [criticalSpeedPaceByYear, setCriticalSpeedPaceByYear] =
    useState<CriticalSpeedPaceByYearResponse | null>(null);
  const [speedYearComparison, setSpeedYearComparison] = useState<DurationCurveYearComparisonResponse | null>(null);
  const [powerCurve, setPowerCurve] = useState<DurationCurveResponse | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setErrors([]);
    const days = PERIOD_DAYS[period];

    const activityQuery = { days, limit: 100, includeTreadmill };
    const results = await Promise.allSettled([
      analyticsApi.getEfficiencyTrends(activityQuery),
      analyticsApi.getDecouplingTrends(activityQuery),
      analyticsApi.getFatigueResistance(activityQuery),
      analyticsApi.getCriticalSpeed(false, includeTreadmill),
      analyticsApi.getCriticalSpeedPaceByYear(3, includeTreadmill),
      analyticsApi.getDurationCurveYearComparison('speed', 3, includeTreadmill),
      analyticsApi.getDurationCurve('power', curveScope, includeTreadmill),
    ]);

    const nextErrors: string[] = [];

    if (results[0].status === 'fulfilled') {
      setEfficiency(results[0].value.activities ?? []);
    } else {
      setEfficiency([]);
      nextErrors.push('Kunne ikke hente Efficiency Factor-trend.');
    }

    if (results[1].status === 'fulfilled') {
      setDecoupling(results[1].value.activities ?? []);
    } else {
      setDecoupling([]);
      nextErrors.push('Kunne ikke hente aerobic decoupling.');
    }

    if (results[2].status === 'fulfilled') {
      setFatigue(results[2].value.activities ?? []);
    } else {
      setFatigue([]);
      nextErrors.push('Kunne ikke hente fatigue resistance.');
    }

    if (results[3].status === 'fulfilled') {
      setCriticalSpeed(results[3].value);
    } else {
      setCriticalSpeed(null);
      nextErrors.push('Kunne ikke hente Critical Speed.');
    }

    if (results[4].status === 'fulfilled') {
      setCriticalSpeedPaceByYear(results[4].value);
    } else {
      setCriticalSpeedPaceByYear(null);
      nextErrors.push('Kunne ikke hente Critical Speed pace per år.');
    }

    if (results[5].status === 'fulfilled') {
      setSpeedYearComparison(results[5].value);
    } else {
      setSpeedYearComparison(null);
      nextErrors.push('Kunne ikke hente speed-duration sammenligning per år.');
    }

    if (results[6].status === 'fulfilled') {
      setPowerCurve(results[6].value);
    } else {
      setPowerCurve(null);
    }

    setErrors(nextErrors);
    setLoading(false);
  }, [period, curveScope, includeTreadmill]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const mergedRows = useMemo(
    () => mergeActivityRows(efficiency, decoupling, fatigue),
    [efficiency, decoupling, fatigue],
  );

  const longRunDecoupling = useMemo(
    () => decoupling.filter((item) => (item.duration ?? 0) >= 45 * 60),
    [decoupling],
  );

  const efChartData = useMemo(
    () => [...efficiency]
      .filter((item) => item.steadyStateEfficiencyFactor != null || item.avgEfficiencyFactor != null)
      .sort((a, b) => new Date(a.startTimeLocal).getTime() - new Date(b.startTimeLocal).getTime())
      .map((item) => ({
        date: item.startTimeLocal,
        steady_state_ef: item.steadyStateEfficiencyFactor ?? item.avgEfficiencyFactor,
        hover_label: item.activityName
          ? `${item.activityName} · ${formatDate(item.startTimeLocal)}`
          : formatDate(item.startTimeLocal),
      })),
    [efficiency],
  );

  const fatigueChartData = useMemo(
    () => [...fatigue]
      .filter((item) => item.fatigueResistanceScore != null)
      .sort((a, b) => new Date(a.startTimeLocal).getTime() - new Date(b.startTimeLocal).getTime())
      .map((item) => ({
        date: item.startTimeLocal,
        fatigue_resistance_score: item.fatigueResistanceScore,
        hover_label: item.activityName
          ? `${item.activityName} · ${formatDate(item.startTimeLocal)}`
          : formatDate(item.startTimeLocal),
      })),
    [fatigue],
  );

  const speedYearChartData = useMemo(() => {
    const series = speedYearComparison?.years ?? [];
    if (series.length === 0) {
      return { rows: [], yearKeys: [] as number[], paceAxis: buildPaceYAxisConfig([]) };
    }

    const yearKeys = series.map((s) => s.year);
    const paceValues: number[] = [];
    const rows = DURATION_CURVE_SECONDS.map((durationSeconds) => {
      const row: Record<string, string | number | null> = {
        duration_label: formatDurationLabel(durationSeconds),
        duration_seconds: durationSeconds,
      };
      series.forEach((yearSeries) => {
        const point = yearSeries.points.find(
          (p) => Number(p.duration_seconds) === durationSeconds,
        );
        const speed = point?.speed_mps ?? null;
        const pace =
          point?.pace_sec_per_km ?? (speed != null && speed > 0 ? 1000 / speed : null);
        row[`pace_${yearSeries.year}`] = pace;
        if (pace != null && Number.isFinite(pace)) {
          paceValues.push(pace);
        }
      });
      return row;
    });

    return { rows, yearKeys, paceAxis: buildPaceYAxisConfig(paceValues) };
  }, [speedYearComparison]);

  const criticalSpeedTableYears = useMemo(() => {
    const years = criticalSpeedPaceByYear?.years ?? [];
    return years.length > 0 ? years : [...CRITICAL_SPEED_TABLE_YEARS];
  }, [criticalSpeedPaceByYear]);

  const criticalSpeedPaceByYearRows = useMemo(() => {
    const apiRows = criticalSpeedPaceByYear?.rows ?? [];
    const apiHasPaces = apiRows.some((row) =>
      Object.values(row.paces_by_year ?? {}).some(
        (cell) => cell?.pace_sec_per_km != null && Number.isFinite(cell.pace_sec_per_km),
      ),
    );
    if (apiHasPaces) {
      return apiRows.map((row) => ({
        duration_label: formatDurationLabel(row.duration_seconds),
        duration_seconds: row.duration_seconds,
        paces_by_year: row.paces_by_year,
      }));
    }

    const series = speedYearComparison?.years ?? [];
    if (series.length > 0) {
      return CRITICAL_SPEED_TABLE_DURATIONS.map((durationSeconds) => {
        const paces_by_year: Record<string, { pace_sec_per_km: number | null } | null> = {};
        series.forEach((yearSeries) => {
          const point = yearSeries.points.find(
            (p) => Number(p.duration_seconds) === durationSeconds,
          );
          const speed = point?.speed_mps ?? null;
          const pace =
            point?.pace_sec_per_km ?? (speed != null && speed > 0 ? 1000 / speed : null);
          if (pace != null) {
            paces_by_year[String(yearSeries.year)] = { pace_sec_per_km: pace };
          }
        });
        return {
          duration_label: formatDurationLabel(durationSeconds),
          duration_seconds: durationSeconds,
          paces_by_year,
        };
      });
    }

    return CRITICAL_SPEED_TABLE_DURATIONS.map((durationSeconds) => ({
      duration_label: formatDurationLabel(durationSeconds),
      duration_seconds: durationSeconds,
      paces_by_year: {} as Record<string, { pace_sec_per_km: number | null } | null>,
    }));
  }, [criticalSpeedPaceByYear, speedYearComparison]);

  const hasCriticalSpeedPaceByYear = useMemo(
    () => criticalSpeedPaceByYearRows.some((row) =>
      criticalSpeedTableYears.some((year) => {
        const cell = row.paces_by_year?.[String(year)];
        return cell?.pace_sec_per_km != null && Number.isFinite(cell.pace_sec_per_km);
      }),
    ),
    [criticalSpeedPaceByYearRows, criticalSpeedTableYears],
  );

  const durationChartData = useMemo(() => {
    const points = powerCurve?.points ?? [];
    return [...points]
      .sort((a, b) => a.duration_seconds - b.duration_seconds)
      .map((point) => ({
        duration_label: formatDurationLabel(point.duration_seconds),
        duration_seconds: point.duration_seconds,
        value: point.power_watts ?? null,
        pace: null,
      }));
  }, [powerCurve]);

  const flaggedRows = useMemo(
    () => mergedRows.filter((row) => row.flags.length > 0).slice(0, 25),
    [mergedRows],
  );

  return (
    <PageContainer>
      <Title>Avansert løpeanalyse</Title>
      <Subtitle>
        Efficiency Factor, aerobic decoupling, Critical Speed, fatigue resistance og duration curves.
      </Subtitle>

      <Controls>
        <FilterButton
          $active={!includeTreadmill}
          onClick={() => setIncludeTreadmill(false)}
        >
          Utendørsaktiviteter
        </FilterButton>
        <FilterButton
          $active={includeTreadmill}
          onClick={() => setIncludeTreadmill(true)}
        >
          Innendørs + utendørs
        </FilterButton>
      </Controls>
      <SmallMeta>
        Kun løpeaktiviteter.
        {includeTreadmill
          ? ' Inkluderer tredemølle og innendørs løp.'
          : ' Kun utendørs løp (gate, sti, bane osv.).'}
      </SmallMeta>

      <Controls>
        {(Object.keys(PERIOD_DAYS) as PeriodKey[]).map((key) => (
          <FilterButton key={key} $active={period === key} onClick={() => setPeriod(key)}>
            {key === 'all' ? 'All tid' : `${key} dager`}
          </FilterButton>
        ))}
      </Controls>

      {errors.length > 0 && (
        <ErrorBox>
          {errors.map((message) => (
            <div key={message}>{message}</div>
          ))}
        </ErrorBox>
      )}

      {loading ? (
        <LoadingText>Laster analyse…</LoadingText>
      ) : (
        <>
          <Section>
            <Card>
              <SectionTitle>Critical Speed og terskelpace</SectionTitle>
              {criticalSpeed?.critical_speed_mps || hasCriticalSpeedPaceByYear ? (
                <>
                  {criticalSpeed?.critical_speed_mps ? (
                    <Grid>
                      <div>
                        <MetricLabel>Critical Speed · siste 12 mnd</MetricLabel>
                        <MetricValue>{formatNumber(criticalSpeed.critical_speed_mps, 3)} m/s</MetricValue>
                      </div>
                      <div>
                        <MetricLabel>Kritisk pace (CS) · siste 12 mnd</MetricLabel>
                        <MetricValue>{formatPaceFromSecPerKm(criticalSpeed.critical_pace_sec_per_km)}</MetricValue>
                      </div>
                      <div>
                        <MetricLabel>D&apos;</MetricLabel>
                        <MetricValue>{formatNumber(criticalSpeed.d_prime, 0)} m</MetricValue>
                      </div>
                      <div>
                        <MetricLabel>Modellkvalitet (R²)</MetricLabel>
                        <MetricValue>
                          {modelQualityLabel(criticalSpeed.model_quality)}
                          {criticalSpeed.model_r2 != null ? ` · ${formatNumber(criticalSpeed.model_r2, 3)}` : ''}
                        </MetricValue>
                      </div>
                    </Grid>
                  ) : null}
                  <SmallMeta>
                    Beste pace per CS-varighet og år. Kortere varigheter uten egen års-PR fylles
                    fra samme økt som lengste effort det året.
                  </SmallMeta>
                  <TableWrap>
                    <Table>
                      <thead>
                        <tr>
                          <th>Varighet</th>
                          {criticalSpeedTableYears.map((year) => (
                            <th key={year}>Pace {year}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {criticalSpeedPaceByYearRows.map((row) => (
                          <tr key={row.duration_seconds}>
                            <td>{row.duration_label}</td>
                            {criticalSpeedTableYears.map((year) => (
                              <td key={year}>
                                {formatPaceFromSecPerKm(
                                  row.paces_by_year?.[String(year)]?.pace_sec_per_km ?? null,
                                )}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </TableWrap>
                </>
              ) : (
                <EmptyState>Ingen Critical Speed-data ennå. Kjør synk/beregning for å fylle snapshot.</EmptyState>
              )}
            </Card>
          </Section>

          <Section>
            <Card>
              <SectionTitle>Speed-duration – sammenligning siste 3 år</SectionTitle>
              <SmallMeta>Beste registrerte fart per varighet.</SmallMeta>
              {speedYearChartData.rows.length > 0 && speedYearChartData.yearKeys.length > 0 ? (
                <>
                  <SmallMeta>
                    {speedYearComparison?.years
                      .map((y) => `${y.year}: ${y.effort_count} effort`)
                      .join(' · ')}
                    {speedYearComparison?.calculated_at
                      ? ` · beregnet ${formatDate(speedYearComparison.calculated_at)}`
                      : ''}
                  </SmallMeta>
                  <ChartBox>
                    <ResponsiveContainer width="100%" height={340}>
                      <LineChart
                        data={speedYearChartData.rows}
                        margin={{ top: 12, right: 24, left: 4, bottom: 8 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="duration_label" />
                        <YAxis
                          reversed
                          width={76}
                          domain={speedYearChartData.paceAxis.domain}
                          ticks={speedYearChartData.paceAxis.ticks}
                          allowDecimals={false}
                          tick={{ fontSize: 12 }}
                          tickFormatter={(value) => formatPaceFromSecPerKm(Number(value))}
                        />
                        <Tooltip
                          formatter={(value: number, name: string) => [
                            formatPaceFromSecPerKm(Number(value)),
                            String(name).replace('pace_', ''),
                          ]}
                          labelFormatter={(label) => `Varighet: ${label}`}
                        />
                        <Legend />
                        {speedYearChartData.yearKeys.map((year, index) => (
                          <Line
                            key={year}
                            type="monotone"
                            dataKey={`pace_${year}`}
                            name={String(year)}
                            stroke={YEAR_LINE_COLORS[index % YEAR_LINE_COLORS.length]}
                            strokeWidth={2}
                            dot={{ r: 3 }}
                            connectNulls
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </ChartBox>
                </>
              ) : (
                <EmptyState>Ingen speed-duration-data for de siste tre årene.</EmptyState>
              )}
            </Card>
          </Section>

          <Section>
            <Card>
              <SectionTitle>Power-duration curve</SectionTitle>
              <Controls>
                {(['all_time', 'last_90_days', 'last_365_days'] as DurationCurveScope[]).map((scope) => (
                  <FilterButton
                    key={scope}
                    $active={curveScope === scope}
                    onClick={() => setCurveScope(scope)}
                  >
                    {scope === 'all_time' ? 'All tid' : scope === 'last_90_days' ? '90 dager' : '365 dager'}
                  </FilterButton>
                ))}
              </Controls>

              {durationChartData.length > 0 ? (
                <>
                  <SmallMeta>
                    {powerCurve?.effort_count ?? 0} beste effort-punkter · beregnet{' '}
                    {formatDate(powerCurve?.calculated_at)}
                  </SmallMeta>
                  <ChartBox>
                    <ResponsiveContainer width="100%" height={320}>
                      <LineChart data={durationChartData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="duration_label" />
                        <YAxis
                          domain={['auto', 'auto']}
                          tickFormatter={(value) => `${Math.round(Number(value))} W`}
                        />
                        <Tooltip
                          formatter={(value: number) => [`${Math.round(value)} W`, 'Power']}
                          labelFormatter={(label) => `Varighet: ${label}`}
                        />
                        <Line
                          type="monotone"
                          dataKey="value"
                          stroke="#3498db"
                          strokeWidth={2}
                          dot={{ r: 4 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </ChartBox>
                </>
              ) : (
                <EmptyState>
                  Ingen power-duration punkter for valgt periode (krever power i FIT-data).
                </EmptyState>
              )}
            </Card>
          </Section>

          <Section>
            <Card>
              <SectionTitle>Efficiency Factor</SectionTitle>
              {efChartData.length > 0 ? (
                <>
                  <ChartBox>
                    <PlotlyChart
                      data={efChartData}
                      xKey="date"
                      yKeys={['steady_state_ef']}
                      title="Steady-state EF over tid"
                      yAxisTitle="EF (m/s per bpm)"
                      textKey="hover_label"
                    />
                  </ChartBox>
                  <TableWrap>
                    <Table>
                      <thead>
                        <tr>
                          <th>Dato</th>
                          <th>Aktivitet</th>
                          <th>Snitt EF</th>
                          <th>Steady-state EF</th>
                          <th>Datakvalitet</th>
                        </tr>
                      </thead>
                      <tbody>
                        {efficiency.slice(0, 20).map((item) => (
                          <tr key={item.activityId}>
                            <td>{formatDate(item.startTimeLocal)}</td>
                            <td>{item.activityName ?? item.activityId}</td>
                            <td>{formatNumber(item.avgEfficiencyFactor, 4)}</td>
                            <td>{formatNumber(item.steadyStateEfficiencyFactor, 4)}</td>
                            <td>{formatNumber(item.efficiencyDataQuality, 0)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </TableWrap>
                </>
              ) : (
                <EmptyState>Ingen lagrede EF-metrics i valgt periode.</EmptyState>
              )}
            </Card>
          </Section>

          <Section>
            <Card>
              <SectionTitle>Aerobic decoupling (langturer ≥ 45 min)</SectionTitle>
              {longRunDecoupling.length > 0 ? (
                <TableWrap>
                  <Table>
                    <thead>
                      <tr>
                        <th>Dato</th>
                        <th>Aktivitet</th>
                        <th>Distanse</th>
                        <th>Decoupling</th>
                        <th>Egnethet</th>
                        <th>Årsak</th>
                      </tr>
                    </thead>
                    <tbody>
                      {longRunDecoupling.slice(0, 25).map((item) => (
                        <tr key={item.activityId}>
                          <td>{formatDate(item.startTimeLocal)}</td>
                          <td>{item.activityName ?? item.activityId}</td>
                          <td>{formatDistanceKm(item.distance)}</td>
                          <td>{formatPercent(item.decouplingPercent)}</td>
                          <td>
                            <Badge
                              $tone={
                                item.decouplingSuitabilityFlag === 'suitable'
                                  ? 'good'
                                  : item.decouplingSuitabilityFlag === 'unsuitable'
                                    ? 'neutral'
                                    : 'neutral'
                              }
                            >
                              {item.decouplingSuitabilityFlag === 'suitable'
                                ? 'Egnet'
                                : item.decouplingSuitabilityFlag === 'unsuitable'
                                  ? 'Ikke egnet'
                                  : '—'}
                            </Badge>
                          </td>
                          <td>{translateDecouplingReasons(item.decouplingReasonIfUnsuitable)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </TableWrap>
              ) : (
                <EmptyState>Ingen decoupling-data for langturer i valgt periode.</EmptyState>
              )}
            </Card>
          </Section>

          <Section>
            <Card>
              <SectionTitle>Fatigue resistance</SectionTitle>
              {fatigueChartData.length > 0 ? (
                <>
                  <ChartBox>
                    <PlotlyChart
                      data={fatigueChartData}
                      xKey="date"
                      yKeys={['fatigue_resistance_score']}
                      title="Fatigue resistance score over tid"
                      yAxisTitle="Score (0–100)"
                      textKey="hover_label"
                    />
                  </ChartBox>
                  <TableWrap>
                    <Table>
                      <thead>
                        <tr>
                          <th>Dato</th>
                          <th>Aktivitet</th>
                          <th>Score</th>
                          <th>Pace-fall</th>
                          <th>Pulsdrift</th>
                          <th>EF-fall</th>
                        </tr>
                      </thead>
                      <tbody>
                        {fatigue.slice(0, 20).map((item) => (
                          <tr key={item.activityId}>
                            <td>{formatDate(item.startTimeLocal)}</td>
                            <td>{item.activityName ?? item.activityId}</td>
                            <td>{formatNumber(item.fatigueResistanceScore, 1)}</td>
                            <td>{formatPercent(item.paceDropPct)}</td>
                            <td>{formatPercent(item.hrDriftPct)}</td>
                            <td>{formatPercent(item.efDropPct)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </TableWrap>
                </>
              ) : (
                <EmptyState>Ingen fatigue resistance-data i valgt periode.</EmptyState>
              )}
            </Card>
          </Section>

          <Section>
            <Card>
              <SectionTitle>Aktivitetsflagg</SectionTitle>
              <SmallMeta>
                Avledet fra decoupling, EF-datakvalitet og fatigue metrics.
              </SmallMeta>
              {flaggedRows.length > 0 ? (
                <TableWrap>
                  <Table>
                    <thead>
                      <tr>
                        <th>Dato</th>
                        <th>Aktivitet</th>
                        <th>Decoupling</th>
                        <th>Fatigue</th>
                        <th>Flagg</th>
                      </tr>
                    </thead>
                    <tbody>
                      {flaggedRows.map((row) => (
                        <tr key={row.activityId}>
                          <td>{formatDate(row.startTimeLocal)}</td>
                          <td>{row.activityName ?? row.activityId}</td>
                          <td>{formatPercent(row.decouplingPercent)}</td>
                          <td>{formatNumber(row.fatigueResistanceScore, 1)}</td>
                          <td>
                            {row.flags.map((flag) => (
                              <Badge key={flag} $tone={FLAG_META[flag].tone}>
                                {FLAG_META[flag].label}
                              </Badge>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </TableWrap>
              ) : (
                <EmptyState>Ingen aktiviteter med flagg i valgt periode.</EmptyState>
              )}
            </Card>
          </Section>
        </>
      )}
    </PageContainer>
  );
}
