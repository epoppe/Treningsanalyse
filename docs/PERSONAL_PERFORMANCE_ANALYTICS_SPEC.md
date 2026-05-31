# Personal Performance Analytics Platform (PPAP)

## Dokumentinformasjon

| Felt | Verdi |
|--------|--------|
| Dokument | Personal Performance Analytics Platform |
| Versjon | 1.0 |
| Status | Ready for Development |
| Målgruppe | Backend-utviklere, Data Engineers, ML Engineers |
| Datakilde | Garmin Connect via Garth |
| Database | Delta Lake / SQL Warehouse |
| Oppdatering | Daglig + etter hver aktivitet |

# 1. Formål

Bygge en analyseplattform som beregner avanserte trenings-, helse-, restitusjons- og prestasjonsmetrikker basert på Garmin-data.

Plattformen skal:
- ingestere rå Garmin-data
- beregne avledede metrikker
- lagre historiske tidsserier
- eksponere metrikker til AI-agenter
- kunne utvides med andre wearables senere

# 2. Arkitektur

```text
Garmin Connect
        │
        ▼
      Garth
        │
        ▼
 Raw Data Layer
        │
        ▼
 Metric Engine
        │
        ▼
 Analytics Layer
        │
        ▼
 AI Insight Layer
```

# 3. Datamodell

## Activity

Primærnøkkel: `activity_id`

Kjernefelter:
- user_id
- activity_id
- activity_type
- start_time
- duration_sec
- distance_m
- elevation_gain_m
- elevation_loss_m
- avg_hr
- max_hr
- avg_power
- max_power
- avg_pace
- avg_cadence
- training_load
- training_stress_score
- vo2max
- temperature
- humidity
- wind_speed
- route_fingerprint

## Daily Health

Primærnøkkel:
- user_id
- date

Felter:
- sleep_score
- sleep_duration_sec
- body_battery
- hrv_rmssd
- resting_hr
- stress_score
- respiration_rate
- weight

# 4. Metric Calculation Engine

Alle beregninger skal være:
- idempotente
- historisk reproduserbare
- inkrementelle ved nye aktiviteter

# 5. Fitness Metrics

## CTL (Chronic Training Load)

Formel:

CTL_today = CTL_yesterday + (TSS_today - CTL_yesterday)/42

Output:
- fitness.ctl

## ATL (Acute Training Load)

ATL_today = ATL_yesterday + (TSS_today - ATL_yesterday)/7

Output:
- fitness.atl

## TSB (Training Stress Balance)

TSB = CTL - ATL

Output:
- fitness.tsb

# 6. Aerobic Efficiency

## Efficiency Factor

Hvis power finnes:

EF = normalized_power / avg_hr

Ellers:

EF = normalized_speed / avg_hr

Output:
- activity.efficiency_factor

## Aerobic Decoupling

decoupling = (EF_second_half - EF_first_half) / EF_first_half

Output:
- activity.decoupling_pct

## Trendserier

- fitness.ef_30d
- fitness.ef_60d
- fitness.ef_90d

# 7. Running Economy

## Economy HR

speed_mps / avg_hr

Output:
- running.economy_hr

## Economy Power

speed_mps / avg_power

Output:
- running.economy_power

# 8. Critical Speed

Input:
- 3 min best effort
- 5 min best effort
- 12 min best effort
- 20 min best effort
- 30 min best effort

Modell:

distance = CS × time + W'

Output:
- running.critical_speed
- running.w_prime

# 9. Running Power Analytics

Power-duration curve:

- power_5s
- power_30s
- power_1m
- power_5m
- power_20m
- power_60m

Output:
- running.critical_power
- running.w_prime_power

# 10. Fatigue Resistance

Komponenter:
- Pace degradation
- Cadence degradation
- Stride degradation
- HR drift

Output:
- running.fatigue_resistance_score (0-100)

# 11. Form Degradation Index

Input:
- cadence
- stride length
- ground contact time
- vertical ratio

Output:
- running.form_degradation_index

# 12. Recovery Analytics

## HRV Baseline

28 dagers median.

Output:
- recovery.hrv_baseline

## HRV Delta

(today - baseline) / baseline

Output:
- recovery.hrv_delta_pct

## Recovery Efficiency

Input:
- TSS
- Sleep Score
- HRV Delta
- Resting HR

Output:
- recovery.recovery_efficiency_score

## Recovery Time Prediction

Output:
- recovery.predicted_hours_to_baseline

# 13. Sleep Analytics

## Sleep Debt

Output:
- sleep_debt_7d
- sleep_debt_14d
- sleep_debt_28d

## Sleep Consistency

Basert på standardavvik i:
- leggetid
- oppvåkningstid

Output:
- sleep.consistency_score

# 14. Cardiovascular Analytics

Output:
- cardio.rhr_7d
- cardio.rhr_30d
- cardio.hrv_7d
- cardio.hrv_30d
- cardio.hrv_90d
- cardio.drift_score

# 15. Load Management

## ACWR

7_day_load / 28_day_load

Output:
- load.acwr

## Monotony

mean(load) / sd(load)

Output:
- load.monotony

## Strain

load × monotony

Output:
- load.strain

## Overtraining Risk

Input:
- ATL
- HRV
- Sleep
- Monotony

Output:
- risk.overtraining_score

# 16. Route Intelligence

## Route Fingerprint

Hash av:
- GPS-geometri
- distanse
- høydemeter

## Benchmarking

Output:
- route.performance_delta_pct
- route.hr_delta_pct
- route.power_delta_pct

# 17. Weather Adjustment

Input:
- temperatur
- luftfuktighet
- vind
- duggpunkt

Output:
- weather.adjusted_pace
- weather.performance_penalty_pct

# 18. Race Prediction

Output:
- predicted_5k_time
- predicted_10k_time
- predicted_half_marathon_time
- predicted_marathon_time

# 19. Training Classification

Klasser:
- Recovery
- Easy
- Aerobic
- Tempo
- Threshold
- VO2Max
- Anaerobic
- Race

Output:
- training.training_zone
- training.aerobic_score
- training.anaerobic_score

# 20. Personal Performance Model

Features:
- HRV
- Sleep
- CTL
- ATL
- Body Battery
- VO2max
- EF
- Decoupling

Output:
- performance_driver_name
- performance_driver_weight

Eksempel:
- HRV = 38%
- Sleep = 24%
- CTL = 17%
- VO2max = 8%

# 21. Daily Composite Scores

Alle normaliseres til 0–100.

Output:
- fitness_score
- fatigue_score
- recovery_score
- readiness_score
- performance_score
- injury_risk_score
- overtraining_score

# 22. API-kontrakt

GET /api/v1/readiness/latest

Eksempelrespons:

```json
{
  "fitness_score": 81,
  "fatigue_score": 42,
  "readiness_score": 88,
  "recovery_score": 76,
  "injury_risk_score": 19
}
```

# 23. Akseptansekriterier

Systemet skal:
- beregne alle metrikker historisk
- oppdatere metrikker innen 5 minutter etter aktivitet
- støtte minimum 5 års historikk
- håndtere manglende power-data
- håndtere manglende HRV-data
- støtte fremtidige datakilder

# 24. Implementeringsfaser

## Fase 1
- CTL
- ATL
- TSB
- EF
- Decoupling
- Recovery
- Sleep
- Composite Scores

## Fase 2
- Critical Speed
- Critical Power
- Fatigue Resistance
- Route Intelligence

## Fase 3
- Race Prediction
- Personal Performance Model
- AI Insight Layer
