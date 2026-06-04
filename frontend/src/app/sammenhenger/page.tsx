'use client';

import { useEffect, useMemo, useState } from 'react';
import styled from 'styled-components';
import { analysisApi, FactorRelationshipMetricMeta, FactorRelationshipsResponse } from '../../utils/api';
import PlotlyChart from '../../components/PlotlyChart';
import { FACTOR_RELATIONSHIP_METRICS } from './metricsCatalog';

const CORRELATION_STRENGTH_NB: Record<string, string> = {
  insufficient: 'For få datapunkter',
  strong: 'Sterk',
  moderate: 'Moderat',
  weak: 'Svak',
  'very weak': 'Svært svak',
};

const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
`;
const Title = styled.h1`color:#2c3e50; margin-bottom:0.5rem;`;
const Subtitle = styled.p`color:#666; margin-bottom:1.5rem;`;
const Controls = styled.div`
  display:grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap:1rem; margin-bottom:1.5rem;
`;
const Card = styled.div`
  background:white; padding:1rem; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.08);
`;
const Label = styled.label`display:block; font-size:0.9rem; color:#555; margin-bottom:0.35rem;`;
const Select = styled.select`width:100%; padding:0.6rem; border:1px solid #ddd; border-radius:6px;`;
const Input = styled.input`width:100%; padding:0.6rem; border:1px solid #ddd; border-radius:6px;`;
const Grid = styled.div`
  display:grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap:1rem; margin-bottom:1.5rem;
`;
const StatValue = styled.div`font-size:1.6rem; font-weight:700; color:#3498db;`;
const Small = styled.div`color:#666; font-size:0.95rem;`;
const ErrorBox = styled.div`background:#fff3f3; color:#a33; padding:1rem; border-radius:8px; margin-bottom:1rem;`;
const ChartCard = styled(Card)`min-height:440px;`;

const AVAILABILITY_LABELS: Record<string, string> = {
  supported: 'Tilgjengelig',
  computed: 'Beregnet',
  not_ingested: 'Ikke ingestet',
  empty_source: 'Tom kilde',
  unsupported: 'Ikke støttet',
};

const getMetricLabel = (meta: FactorRelationshipMetricMeta) => {
  if (!meta.availability || meta.selectable !== false) {
    return meta.label;
  }
  const availabilityText = AVAILABILITY_LABELS[meta.availability] ?? meta.availability;
  return `${meta.label} (${availabilityText})`;
};

export default function SammenhengerPage() {
  const [data, setData] = useState<FactorRelationshipsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [xMetric, setXMetric] = useState('sleep_score');
  const [yMetric, setYMetric] = useState('training_stress_score');
  const [days, setDays] = useState(90);
  const [activityType, setActivityType] = useState('');
  const [minDistanceKm, setMinDistanceKm] = useState(3);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    analysisApi.getFactorRelationships({ xMetric, yMetric, days, activityType, minDistanceKm })
      .then((result) => { if (active) setData(result); })
      .catch((err) => { if (active) setError(err?.message || 'Kunne ikke hente sammenhenger'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [xMetric, yMetric, days, activityType, minDistanceKm]);

  const metricOptions = useMemo(() => {
    const fromApi = data?.available_metrics;
    if (fromApi && Object.keys(fromApi).length > 0) {
      return Object.entries(fromApi);
    }
    return Object.entries(FACTOR_RELATIONSHIP_METRICS);
  }, [data]);

  const selectableMetricOptions = useMemo(
    () => metricOptions.filter(([, meta]) => meta.selectable !== false),
    [metricOptions],
  );

  const metricLookup = useMemo(() => new Map(metricOptions), [metricOptions]);

  useEffect(() => {
    if (metricOptions.length === 0 || selectableMetricOptions.length === 0) {
      return;
    }

    const currentX = metricLookup.get(xMetric);
    if (currentX?.selectable === false) {
      const fallback = selectableMetricOptions.find(([key]) => key !== yMetric)?.[0] ?? selectableMetricOptions[0][0];
      if (fallback && fallback !== xMetric) {
        setXMetric(fallback);
      }
    }

    const currentY = metricLookup.get(yMetric);
    if (currentY?.selectable === false) {
      const fallback = selectableMetricOptions.find(([key]) => key !== xMetric)?.[0] ?? selectableMetricOptions[0][0];
      if (fallback && fallback !== yMetric) {
        setYMetric(fallback);
      }
    }
  }, [metricLookup, metricOptions, selectableMetricOptions, xMetric, yMetric]);

  const scatterData = useMemo(() => {
    if (!data?.points?.length) return [];
    return data.points.map((p) => ({
      date: p.date,
      x: p.x,
      y: p.y,
      hover_label: p.activity_name
        ? `${p.activity_name}${p.date ? ` · ${p.date}` : ''}`
        : (p.date ?? ''),
    }));
  }, [data]);

  const xAxisTitle = useMemo(() => {
    if (!data?.x_meta) return 'Dato';
    const { label, unit } = data.x_meta;
    return unit ? `${label} (${unit})` : label;
  }, [data]);

  const yAxisTitle = useMemo(() => {
    if (!data?.y_meta) return '';
    const { label, unit } = data.y_meta;
    return unit ? `${label} (${unit})` : label;
  }, [data]);

  const xMetricMeta = metricLookup.get(xMetric);
  const yMetricMeta = metricLookup.get(yMetric);

  return (
    <Container>
      <Title>Sammenhenger mellom faktorer</Title>
      <Subtitle>
        Helsemetrikker (søvn, HRV, body battery, stress) hentes fra dagen før aktivitetens startdato
        (typisk natten før økta). Treningsmålinger (TSS, distanse, puls, …) kommer fra selve aktiviteten.
      </Subtitle>

      <Controls>
        <Card>
          <Label>X-akse</Label>
          <Select value={xMetric} onChange={(e) => setXMetric(e.target.value)}>
            {metricOptions.map(([key, meta]) => (
              <option key={key} value={key} disabled={meta.selectable === false}>
                {getMetricLabel(meta)}
              </option>
            ))}
          </Select>
          {xMetricMeta?.selectable === false && xMetricMeta.availability_reason && (
            <Small style={{ marginTop: '0.5rem' }}>{xMetricMeta.availability_reason}</Small>
          )}
        </Card>
        <Card>
          <Label>Y-akse</Label>
          <Select value={yMetric} onChange={(e) => setYMetric(e.target.value)}>
            {metricOptions.map(([key, meta]) => (
              <option key={key} value={key} disabled={meta.selectable === false}>
                {getMetricLabel(meta)}
              </option>
            ))}
          </Select>
          {yMetricMeta?.selectable === false && yMetricMeta.availability_reason && (
            <Small style={{ marginTop: '0.5rem' }}>{yMetricMeta.availability_reason}</Small>
          )}
        </Card>
        <Card>
          <Label>Periode (dager)</Label>
          <Input type="number" value={days} min={14} max={365} onChange={(e) => setDays(Number(e.target.value) || 90)} />
        </Card>
        <Card>
          <Label>Aktivitetstype</Label>
          <Select value={activityType} onChange={(e) => setActivityType(e.target.value)}>
            <option value="">Alle aktivitetstyper</option>
            <option value="running">Løping</option>
            <option value="cycling">Sykling</option>
            <option value="walking">Gåing</option>
            <option value="trail_running">Terrengløp</option>
          </Select>
        </Card>
        <Card>
          <Label>Min. distanse (km)</Label>
          <Input type="number" value={minDistanceKm} min={0} step={0.5} onChange={(e) => setMinDistanceKm(Number(e.target.value) || 0)} />
        </Card>
      </Controls>

      {error && <ErrorBox>{error}</ErrorBox>}

      <Grid>
        <Card><Small>Datapunkter</Small><StatValue>{loading ? '…' : (data?.point_count ?? 0)}</StatValue></Card>
        <Card>
          <Small>Korrelasjon (Pearson)</Small>
          <StatValue>
            {loading ? '…' : (typeof data?.correlation === 'number' ? data.correlation.toFixed(4) : '–')}
          </StatValue>
        </Card>
        <Card>
          <Small>Styrke</Small>
          <StatValue>
            {loading ? '…' : (
              data?.correlation_strength
                ? (CORRELATION_STRENGTH_NB[data.correlation_strength] ?? data.correlation_strength)
                : '–'
            )}
          </StatValue>
        </Card>
        <Card><Small>Gj.snitt X / Y</Small><StatValue style={{fontSize:'1.1rem'}}>{loading ? '…' : `${data?.summary.avg_x ?? '–'} / ${data?.summary.avg_y ?? '–'}`}</StatValue></Card>
      </Grid>

      <ChartCard>
        {loading ? <Small>Laster analyse…</Small> : (
          scatterData.length > 0 ? (
            <PlotlyChart
              data={scatterData}
              xKey="x"
              yKeys={["y"]}
              title={`${data?.x_meta.label} vs ${data?.y_meta.label}`}
              yAxisTitle={yAxisTitle}
              xAxisTitle={xAxisTitle}
              traceMode="markers"
              textKey="hover_label"
            />
          ) : <Small>Ingen datapunkter med både X og Y for valgte filtre. Prøv flere dager, lavere min. distanse eller en annen aktivitetstype.</Small>
        )}
      </ChartCard>
    </Container>
  );
}
