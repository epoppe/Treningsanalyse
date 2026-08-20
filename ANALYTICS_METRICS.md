# Avanserte løpemetrics (EF og Aerobic Decoupling)

Dette dokumentet beskriver formlene bak Efficiency Factor (EF) og aerobic decoupling i backend.

**Aktivitetsfilter:** Løpeanalyse inkluderer kun utendørs-lignende løp: `running`, `trail_running`, `street_running` og `track_running`. Tredemølle, innendørs, langrenn, sykling og andre typer ekskluderes.

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
- `GET /api/analytics/critical-speed?include_treadmill=false|true` — Critical Speed for utendørs løp eller utendørs + innendørs/tredemølle (kun løpeaktiviteter)
- `GET /api/analytics/fatigue-resistance?days=&limit=` — per-aktivitet fatigue resistance for lagrede langturer
- `GET /api/analytics/duration-curve?metric=speed|power&scope=all_time|last_90_days|last_365_days` — beste duration curve-punkter

## Critical Speed

GPS-spikes filtreres før beregning:

- Enkelt-sample fart klippes til max(median × 2,5, 8,5 m/s) per aktivitet
- Beste snittfart per vindu må ligge under varighetsavhengig tak (f.eks. max 8,0 m/s på 3 min, 6,5 m/s på 30 min)

Critical Speed beregnes fra **siste 12 måneder** (365 dager) på tvers av løpeøkter, fra beste snittfart for disse varighetene:

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
Økten må være minst **45 min totalt** (Garmin-varighet/FIT-span); sammenligningen bruker data etter
10 min oppvarming og krever minst **30 min** gyldig tid der.

Tidlig del sammenlignes med sen del:

| Felt | Beskrivelse |
|------|-------------|
| `fatigue_resistance_score` | 0–100, høyere er bedre |
| `pace_drop_pct` | Fartsfall sen vs tidlig del |
| `hr_drift_pct` | Pulsdrift sen vs tidlig del |
| `cadence_drop_pct` | Kadensfall sen vs tidlig del |
| `ef_drop_pct` | EF-fall sen vs tidlig del |

## Speed-/Power-Duration Curve

**Årssammenligning:** `GET /api/analytics/duration-curve/year-comparison?metric=speed&years=3` returnerer beste speed-punkter per kalenderår (siste tre år som standard) for én graf med flere linjer.

Duration curve bruker disse varighetene:

- 30 s
- 1 min
- 3 min
- 5 min
- 10 min
- 20 min
- 40 min
- 60 min

For hver varighet lagres beste kjente punkt for:

- `all_time`
- `last_90_days`
- `last_365_days`

Speed curve beregnes alltid når fart finnes. Power curve beregnes bare når FIT-samples inneholder `power`.

## Adaptive Coaching Engine v2

Coaching-laget utvider regelbasert analyse med personlig, longitudinal og evidensbevisst beslutningsstøtte:

| Service | Rolle |
|---------|-------|
| `SessionClassifierService` | Klassifiserer løpeøkter (recovery, easy, threshold, VO2, race, …) med confidence og evidence |
| `TrendAnalysisService` | Longitudinal trender (7/28/90/365 d) for VO2max, CTL, HRV, EF, durability m.m. |
| `AdaptiveThresholdService` | LT1-estimat med prioritert evidenskjede; LT2-multiplikator som fallback |
| `TrainingResponseService` | Historisk load→response (korrelasjon, ikke kausalitet) |
| `NextBestWorkoutService` | Neste økt med guardrails (ingen harde dager på rad uten sterk grunn) |
| `CoachingBacktestService` | As-of evaluering uten fremtidslekkasje |

### Evidence-typer (`metric_evidence.py`)

| `source_type` | Betydning |
|---------------|-----------|
| `measured` | Direkte målt (f.eks. lab) |
| `garmin` | Levert av Garmin-enhet/konto |
| `derived` | Beregnet fra normaliserte data (FIT, aktivitetsfelt) |
| `estimated` | Modell/heuristikk med usikkerhet |
| `heuristic` | Regelbasert score uten kalibrering |
| `model` | Prediksjon fra treningsmodell |

**PB readiness:** `pb_probability` i API er beholdt for bakoverkompatibilitet, men er en heuristisk `pb_readiness_score` (0–100) — **ikke** en kalibrert sannsynlighet. Se `pb_probability_semantics` i coaching snapshot.

### MCP-moduler (`backend/app/mcp/tools/`)

| Modul | Innhold |
|-------|---------|
| `shared.py` | Felles implementasjon (katalog, recovery-hjelpere, timeseries) |
| `profile.py` | `athlete_profile`, recovery, readiness |
| `activities.py` | Aktivitetsliste og deep dive |
| `routes.py` | Rute-sammenligning |
| `metrics.py` | Metrikk-katalog og timeseries |
| `coaching.py` | Coaching v2/v3-verktøy (neste økt, klassifisering, backtest, decision brief, evaluation) |
| `common.py` | Delt context/parsing |

`training_tools.py` er backwards-compatible facade.

### PB-sannsynlighet (kalibrert)

`PbProbabilityCalibrationService` binner historisk `pb_readiness_score` mot faktiske PB-er per distanse og returnerer empirisk `pb_rate_pct` når n≥8 løp. `get_pb_probability()` bruker kalibrering når tilgjengelig, ellers readiness-heuristikk. Metadata i `pb_calibrated_probability` og `pb_probability_semantics`.

## Adaptive Coaching Engine v3

v3 bygger på v2 uten å erstatte eksisterende services. Fokus: personlig kalibrering, outcome-validering, sammenlignbare økter og transparent beslutningskjede.

| Service | Rolle |
|---------|-------|
| `SessionQualityService` | Type-spesifikk øktkvalitet 0–100 (ikke krysstype-sammenlignbar) |
| `ComparableSessionService` | Finn «like» historiske økter; percentile mot personlig baseline |
| `RecommendationOutcomeService` | Kobler anbefaling ↔ faktisk oppfølging; skiller adherence / outcome / counterfactual |
| `AthleteCalibrationService` | Individuelle terskler kun ved sterk evidens (ellers default) |
| `LoadVariabilityService` | Monotoni, strain, hard-day densitet — supplement til CTL/ATL/TSB (ikke ACWR-skade) |
| `ContextAdjustedTrendService` | Prestasjonstrender justert for varme, høyde m.m. |
| `CalibrationReportService` | Confidence-bins vs empirisk treffsikkerhet |
| `AthleteStateService` | Separate dimensjoner (fitness, fatigue, recovery, …) uten opaque superscore |
| `CoachingModelHealthService` | `healthy` / `degraded` / `insufficient_data` |
| `CoachingEvaluationService` | Maskinlesbart evaluation-payload for senere dashboard |

`NextBestWorkoutService` returnerer nå `decision_trace` og `load_variability`.

### Nye MCP-verktøy

| Tool | Formål |
|------|--------|
| `training_decision_brief` | Kompakt executive-pakke (state + anbefaling + trace) |
| `session_quality` | Kvalitet for én aktivitet |
| `comparable_sessions` | Personlig baseline-sammenligning |
| `coaching_evaluation_report` | Evaluation payload |

Alle historiske evalueringer er `as_of_date`-safe (ingen fremtidslekkasje).

## Adaptive Coaching Engine v4

v4 er preskriptiv og målstyrt. Den bygger på v2/v3 uten nye parallelle score-systemer.

Beslutningskjede: AthleteState → PersonalCalibration → Goal/Phase → kandidater → guardrails → ranking → WorkoutPrescription → ukeplan → outcome.

| Service | Rolle |
|---------|-------|
| `AthleteCalibrationService.get_parameter` | Resolved terskel med `threshold_source` (personalized kun ved evidensgate) |
| `IntensityPrescriptionService` | Kanoniske soner: threshold via LT2/CS, ikke LT1±5% |
| `GoalContextService` | Mål fra konfigurasjon; `goal_feasibility` uten å anta at target_time er realistisk |
| `TrainingPhaseService` | recovery/base/build/specific/peak/taper/maintenance — ikke kalender alene |
| `RaceCapabilityService` | Kapasitetsgap mot løpsmål |
| `WorkoutPrescriptionService` | Konkret økt (sett, pause, HR/pace/RPE + source) |
| `WorkoutCandidateRanker` | Eksplisitte komponenter; guardrails = eligibility |
| `WeeklyPlanService` / `PlanAdaptationService` | Rullerende uke + closed-loop justering |
| `WorkoutEffectivenessService` | Observasjonell lag-respons (ikke kausalitet) |
| `CoachingBacktestV4Service` | old vs v4 uten å erklære vinner uten data |

ACWR er diagnostisk i decision_trace, ikke primær guardrail. Lastbeslutninger bruker load variability, hard-day density, spacing og individuell lasttoleranse.

`training_decision_brief` MCP returnerer goal, phase, prescription, kandidater, ukeplan, evidence_strength og recommendation_confidence.

Mål konfigureres i `.env` (`ATHLETE_GOAL_*`) uten DB-migrering.

## Adaptive Coaching Engine v5

v5 er closed-loop: immutable anbefalinger, faktisk gjennomføring, prospektiv validering og planlegging mot ekte tilgjengelighet.

Historisk backtest ≠ recorded prospective recommendation ≠ observed execution ≠ observed outcome ≠ counterfactual.

| Service | Rolle |
|---------|-------|
| `RecommendationLedgerService` | Persistent `RecommendationRecord` med modellproveniens. Preview/backtest persist=false |
| `RecommendationOutcomeService.evaluate_recorded_recommendation` | Kanonisk prospektiv evaluering |
| `RecommendationOutcomeService.simulate_as_of` | Eksplisitt backtest (regenererer dagens modell) |
| `RecommendationExecutionService` | Kobler aktivitet til nærmeste anbefaling (`followed/modified/skipped/replaced/unplanned`) |
| `WorkoutExecutionAnalysisService` | Plan vs FIT/laps. Adherence ≠ kvalitet |
| `AthleteFeedback` / `PerceivedLoadService` | Valgfri RPE; mismatch mot TSS/EPOC |
| `TrainingAvailability` / `WeeklyPlanOptimizer` | Kalender + scores, ikke faste rest-offsets |
| `ProjectedAthleteStateService` | Fremtidige dager er `projected`, ikke observert HRV |
| `PlanSimulationService` | Last/CTL/ATL/TSB-projeksjon uten VO2max-prediksjon |
| `TrainingPlan` + `TrainingPlanVersion` | Planversjonering ved replanning |
| `CalibrationSnapshot` / `PersonalizationStabilityService` | Hysteresis og drift (`stable/watch/unstable`) |
| `CrossTrainingLoadService` | Kardio vs løpsspesifikk vs muskel/skjelett-last |
| `MusculoskeletalReadinessService` | `good/caution/low` — ikke skadeprediksjon |
| `DecisionRegretService` | `observational_counterfactual_proxy` |
| `TrainingExperiment` | Starter aldri uten `user_confirmed` |

`training_decision_brief` v5 legger til `current_recommendation_id`, `plan.id/version`, `decision_status`, `projected_week`, `recent_execution/feedback`, `personalization_stability` og `prospective_learning`.

## Migrering

Kjør idempotent migrering:

```bash
python backend/migrate_add_advanced_running_metrics.py
```
