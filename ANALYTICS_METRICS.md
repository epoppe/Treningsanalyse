# Avanserte løpemetrics (EF og Aerobic Decoupling)

Dette dokumentet beskriver formlene bak Efficiency Factor (EF) og aerobic decoupling i backend.

## Efficiency Factor (EF)

Per sample:

```
EF_sample = speed_mps / heart_rate
```

Aggregater lagres på `Activity`:

| Felt | Beskrivelse |
|------|-------------|
| `avg_efficiency_factor` | Gjennomsnitt av gyldige per-sample EF |
| `median_efficiency_factor` | Median av per-sample EF |
| `steady_state_efficiency_factor` | Gjennomsnitt EF på samples med fart ±10 % av medianfart |
| `efficiency_data_quality` | Score 0–100 basert på datadekning etter filtrering |

### Filtrering før beregning

- Første **10 minutter** droppes (warmup)
- Stopp/pauser: fart under 0,5 m/s
- Samples uten puls
- Svært lav fart: under 1,0 m/s
- Åpenbare pulsfeil: avvik > 35 bpm fra lokal median (5-sample vindu)
- Puls utenfor 40–220 bpm

Power kan utvides senere; speed/HR er primær kilde nå.

## Aerobic Decoupling

Aktiviteten deles i to **tidsmessige halvdeler** etter filtrering.

```
EF_first  = mean(EF_sample) for første halvdel
EF_second = mean(EF_sample) for andre halvdel

decoupling_pct = ((EF_first - EF_second) / EF_first) * 100
```

Positiv verdi betyr lavere effektivitet (høyere puls relativt til fart) i andre halvdel.

Lagres som `decoupling_percent` (bakoverkompatibel med eksisterende API).

### Egnethet (suitability)

| Felt | Beskrivelse |
|------|-------------|
| `decoupling_suitability_flag` | `suitable` eller `unsuitable` |
| `decoupling_reason_if_unsuitable` | Kommaseparerte årsaker, f.eks. `too_short,interval_like_pace` |
| `decoupling_data_quality_score` | Score 0–100 for datadekning |

Flagges som **unsuitable** ved:

- For kort varighet (< 45 min total / < 40 min gyldig data)
- Intervall-lignende / svært variabel fart (CV > 20 %)
- For mange stopp (> 20 % av samples)
- For mye manglende puls (> 25 %)
- Svært kupert løp (> 30 m stigning per km, uten justering)
- For få gyldige samples (< 20)

## API

- `GET /api/activities/{id}/efficiency` — beregner/returnerer EF + decoupling for én aktivitet
- `GET /api/activities/{id}/decoupling` — eksisterende decoupling-respons (uendret shape)
- `GET /api/analytics/efficiency?days=&limit=` — trend/liste med lagrede EF-felt
- `GET /api/analytics/decoupling?days=&limit=` — trend/liste med lagrede decoupling-felt
- `GET /api/analytics/critical-speed` — siste lagrede Critical Speed snapshot
- `GET /api/analytics/fatigue-resistance?days=&limit=` — per-aktivitet fatigue resistance for lagrede langturer
- `GET /api/analytics/duration-curve?metric=speed|power&scope=all_time|last_90_days|last_365_days` — beste duration curve-punkter

## Critical Speed

Critical Speed beregnes på tvers av løpeøkter fra beste snittfart for disse varighetene:

- 3 min
- 6 min
- 12 min
- 20 min
- 30 min

Modellen er lineær:

```
distance = critical_speed_mps * time_seconds + d_prime
```

Lagret snapshot returnerer:

| Felt | Beskrivelse |
|------|-------------|
| `critical_speed_mps` | Estimert Critical Speed |
| `critical_pace_sec_per_km` | Tilsvarende pace |
| `d_prime` | Intercept i meter |
| `model_r2` | Forklaringsgrad for lineær modell |
| `model_quality` | `good`, `fair`, `low` eller `insufficient_data` |

## Fatigue Resistance

Fatigue Resistance beregnes per langøkt fra filtrerte FIT-samples etter warmup.
Tidlig del sammenlignes med sen del:

| Felt | Beskrivelse |
|------|-------------|
| `fatigue_resistance_score` | 0–100, høyere er bedre |
| `pace_drop_pct` | Fartsfall sen vs tidlig del |
| `hr_drift_pct` | Pulsdrift sen vs tidlig del |
| `cadence_drop_pct` | Kadensfall sen vs tidlig del |
| `ef_drop_pct` | EF-fall sen vs tidlig del |

## Speed-/Power-Duration Curve

Duration curve bruker disse varighetene:

- 5 s
- 30 s
- 1 min
- 3 min
- 5 min
- 10 min
- 20 min
- 60 min

For hver varighet lagres beste kjente punkt for:

- `all_time`
- `last_90_days`
- `last_365_days`

Speed curve beregnes alltid når fart finnes. Power curve beregnes bare når FIT-samples inneholder `power`.

## Migrering

Kjør idempotent migrering:

```bash
python backend/migrate_add_advanced_running_metrics.py
```
