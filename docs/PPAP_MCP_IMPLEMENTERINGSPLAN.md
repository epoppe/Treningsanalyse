# PPAP → MCP: gap-analyse og implementeringsplan

**Branch:** `cursor/nye-metrikker-0f7c`  
**Dato:** 2026-05-31  
**Mål:** Alle metrikker i PPAP-spesifikasjonen skal kunne nås via MCP (`metric_catalog` + `query_metric_timeseries` + relevante coaching-verktøy).

---

## 1. Nåværende MCP-arkitektur (kort)

| Lag | Fil / modul | Rolle |
|-----|-------------|--------|
| Transport | `backend/mcp_server.py` | stdio MCP, verktøy og ressurser |
| Verktøy | `backend/app/mcp/training_tools.py` | Coaching, aktiviteter, `metric_catalog`, timeseries |
| Lagrede metrikker | `METRIC_CATALOG` + auto-discovery fra SQLAlchemy-modeller | DB-kolonner → `activity.*`, `health.*`, `performance.*` |
| Avledede metrikker | `McpDerivedMetricsService` / `DERIVED_METRIC_CATALOG` | On-the-fly beregning for MCP |
| Coaching | `CoachingAnalysisService` | Banister 42/7, polarisert, LT1/LT2, HRV |
| Prestasjon | `PerformanceMetricsService` | Critical speed, fatigue resistance, power-duration |
| Aktivitetsberegning | `AnalysisService` + `CacheCalculationService` | EF, decoupling, negative split, running economy |

**Eksisterende MCP-verktøy (9):** `athlete_profile`, `analyze_recent_training`, `training_readiness_check`, `list_recent_activities`, `activity_deep_dive`, `route_comparison`, `compare_recent_runs`, `metric_catalog`, `query_metric_timeseries`.

---

## 2. Statusmatrise: PPAP vs. repo

Legende: ✅ finnes og kan eksponeres | ⚠️ delvis / annen formel eller navn | ❌ mangler | 🔧 justeres

### 2.1 Fitness / load (kap. 5, 15, 21)

| PPAP-nøkkel | Status | I dag | MCP i dag | Tiltak |
|-------------|--------|-------|-----------|--------|
| `fitness.ctl` | ⚠️ | `TrainingStressService` (EMA 42d på TSS) + Banister «fitness» i coaching | Indirekte via `analyze_recent_training`; ikke i katalog | Legg til `fitness.ctl` / `fitness.atl` / `fitness.tsb` i `DERIVED_METRIC_CATALOG` (daglig scope), koble til `TrainingStressService` |
| `fitness.atl` | ⚠️ | EMA 7d på TSS | — | Samme |
| `fitness.tsb` | ⚠️ | CTL − ATL («Form») | — | Samme; alias `fitness.form` |
| `load.acwr` | ✅ | Garmin ACWR + coaching fallback | `load.acwr` | Dokumenter prioritet Garmin → egen ACWR |
| `load.monotony` | ✅ | `McpDerivedMetricsService` | `load.monotony` | OK |
| `load.strain` | ✅ | idem | `load.strain` | OK |
| `risk.overtraining_score` | ✅ | Heuristikk | `risk.overtraining_score` | Kalibrer mot PPAP-input (ATL, HRV, søvn) i fase 1 |
| `fitness_score` … `overtraining_score` | ⚠️ | Avledet fra Banister/HRV-heuristikk | `fitness_score`, `fatigue_score`, … | Align formler med PPAP (0–100); vurder persist i `AnalyticsSnapshot` |

### 2.2 Aerobic efficiency (kap. 6)

| PPAP-nøkkel | Status | I dag | MCP i dag | Tiltak |
|-------------|--------|-------|-----------|--------|
| `activity.efficiency_factor` | ⚠️ | `avg_efficiency_factor` (m/s per bpm, ikke power/HR) | `activity.avg_efficiency_factor` (auto) | Legg til eksplisitt `activity.efficiency_factor`; power-variant når `normalized_power` finnes |
| `activity.decoupling_pct` | ✅ | `decoupling_percent` på aktivitet | `activity.decoupling_percent` | Alias `activity.decoupling_pct` i katalog |
| `fitness.ef_30d` / `_60d` / `_90d` | ❌ | Kun per-aktivitet + API `/analytics/efficiency` | — | Ny `MetricRollupService`: rullerende median/snitt av EF på løp |

### 2.3 Running economy (kap. 7)

| PPAP-nøkkel | Status | I dag | MCP i dag | Tiltak |
|-------------|--------|-------|-----------|--------|
| `running.economy_hr` | ⚠️ | `running_economy` = (km/h/HR)×100 (annen skala) | `activity.running_economy` (auto) | Standardiser til `speed_mps / avg_hr`; behold gammel som `activity.running_economy_legacy` eller migrer |
| `running.economy_power` | ❌ | — | — | Beregn når power + fart finnes |

### 2.4 Critical speed / power (kap. 8–9)

| PPAP-nøkkel | Status | I dag | MCP i dag | Tiltak |
|-------------|--------|-------|-----------|--------|
| `running.critical_speed` | ✅ | `PerformanceMetricsService`, snapshot | Kun via race-predictions | Eksponer `running.critical_speed`, `running.w_prime` (snapshot/daily) |
| `running.w_prime` | ✅ | `d_prime` i CS-modell | — | Samme |
| `power_5s` … `power_60m` | ⚠️ | `SPEED_CURVE_DURATIONS` (fart, ikke power) | — | Utvid duration curve til power når data finnes |
| `running.critical_power` | ❌ | — | — | Fase 2: CP-modell parallelt med CS |

### 2.5 Fatigue / form (kap. 10–11)

| PPAP-nøkkel | Status | I dag | MCP i dag | Tiltak |
|-------------|--------|-------|-----------|--------|
| `running.fatigue_resistance_score` | ✅ | `PerformanceMetricsService` | `activity.fatigue_resistance_score` | Eksponer i `activity_deep_dive` |
| `running.form_degradation_index` | ❌ | GCT, cadence, stride, vertical_ratio i DB | — | Ny beregning i `PerformanceMetricsService`; aktivitets-scope MCP |

### 2.6 Recovery / sleep / cardio (kap. 12–14)

| PPAP-nøkkel | Status | I dag | MCP i dag | Tiltak |
|-------------|--------|-------|-----------|--------|
| `recovery.hrv_baseline` | ⚠️ | 60d mean i coaching; 28d i spec | `cardio.hrv_*` rullerende | Legg til `recovery.hrv_baseline` (28d median), `recovery.hrv_delta_pct` |
| `recovery.recovery_efficiency_score` | ❌ | Delvis i `_recovery_score` | `recovery_score` (annen def.) | Egen formel TSS + søvn + HRV + RHR |
| `recovery.predicted_hours_to_baseline` | ❌ | — | — | Fase 2 heuristikk |
| `sleep_debt_7d` / `_14d` / `_28d` | ❌ | Søvndata i `Sleep` | `health.sleep_*` | Ny `SleepAnalyticsService` |
| `sleep.consistency_score` | ❌ | — | — | Fra leggetid/oppvåkning i `Sleep` |
| `cardio.rhr_7d` / `rhr_30d` | ❌ | `RestingHeartRate` rå | `health.resting_heart_rate` | Rullerende serier i derived catalog |
| `cardio.hrv_7d` … `hrv_90d` | ✅ | Derived | ✅ | OK |
| `cardio.drift_score` | ✅ | Derived | ✅ | OK |

### 2.7 Route / weather / race / training class (kap. 16–19)

| PPAP-nøkkel | Status | I dag | MCP i dag | Tiltak |
|-------------|--------|-------|-----------|--------|
| Route fingerprint | ✅ | `ActivityRouteFingerprint` | auto `route_fingerprint.*` | OK |
| `route.*_delta_pct` | ✅ | Derived | ✅ | OK |
| `weather.adjusted_pace` | ⚠️ | Kun temperatur-heuristikk | ✅ | Utvid med humidity, wind, dew point fra `Activity` |
| `predicted_*_time` | ✅ | Fra CS | snapshot MCP | OK |
| `training.training_zone` | ⚠️ | 3 soner (LT1/LT2) | ✅ | Utvid til PPAP-klasser (Recovery…Race) eller dokumenter mapping |
| `training.aerobic_score` / `anaerobic_score` | ✅ | Garmin load + fallback | ✅ | OK |

### 2.8 Personal performance model (kap. 20)

| PPAP-nøkkel | Status | I dag | MCP i dag | Tiltak |
|-------------|--------|-------|-----------|--------|
| `performance_driver_name` / `_weight` | ⚠️ | Enkel regelbasert driver | snapshot | Utvid features (CTL, ATL, EF, decoupling); valgfritt persist daglig |

### 2.9 API (kap. 22)

| Endepunkt | Status | Tiltak |
|-----------|--------|--------|
| `GET /api/v1/readiness/latest` | ❌ | Ny router som returnerer samme kompositter som MCP `readiness_score` etc.; MCP kan kalle samme service |

---

## 3. Hva bør justeres (prioritert)

1. **Én sannhet for CTL/ATL/TSB** – I dag: Banister (coaching) vs. `TrainingStressService` (readiness). PPAP og MCP bør bruke samme EMA på daglig TSS.
2. **Navnekonvensjon** – PPAP bruker `fitness.*`, `running.*`, `recovery.*`. MCP har blanding (`activity.*`, `cardio.*`, flat `fitness_score`). Plan: prefixed keys i `DERIVED_METRIC_CATALOG` + aliases i `metric_catalog`.
3. **Efficiency factor** – Spec: power/HR eller speed/HR. Repo: m/s per bpm. Juster beregning og eksponer begge der data finnes.
4. **Running economy** – Harmonisér formel og enhet i MCP (`running.economy_hr`).
5. **Weather** – Kolonner `humidity`, `temperature` finnes; vind/duggpunkt må verifiseres i sync/FIT.
6. **Heuristikk-flagg** – Behold `heuristic: true` i katalog for AI (allerede på flere derived metrics).
7. **Persist vs. on-the-fly** – Tunge beregninger (CS, fatigue) bør caches i `AnalyticsSnapshot` / aktivitetskolonner; MCP leser cache først (allerede mønster for CS).

---

## 4. Implementeringsfaser (tilpasset SQLite + eksisterende stack)

### Fase 1 – MCP-dekning for «kjerne-PPAP» (anbefalt først)

**Mål:** Alt i PPAP kap. 5–6, 12–16, 19–21 querybart via MCP.

| # | Oppgave | Moduler |
|---|---------|---------|
| 1.1 | `PpapMetricsService` – felles beregninger (CTL/ATL/TSB, EF-rollups, RHR-rollups, HRV baseline/delta) | Ny service; bruk `TrainingStressService`, `AnalysisService` |
| 1.2 | Utvid `DERIVED_METRIC_CATALOG` med ~25 nye nøkler (se tabell 2) | `mcp_derived_metrics_service.py` |
| 1.3 | Whitelist eksplisitte aktivitetsfelt i `METRIC_CATALOG` (EF, economy, decoupling alias) | `training_tools.py` |
| 1.4 | `readiness/latest` REST + delt `ReadinessCompositeService` | Ny router `readiness.py` |
| 1.5 | Utvid `athlete_profile` / `training_readiness_check` med CTL/ATL/TSB og kompositter | `training_tools.py` |
| 1.6 | Tester | `test_mcp_training_tools.py`, `test_ppap_metrics.py` |

**Akseptanse:** `metric_catalog` lister alle fase-1-nøkler; `query_metric_timeseries` returnerer data for siste 90 dager der kilde finnes.

### Fase 2 – Løp/spesifikke og power

| # | Oppgave |
|---|---------|
| 2.1 | `running.critical_speed`, `running.w_prime` i MCP (snapshot) |
| 2.2 | `running.form_degradation_index` |
| 2.3 | Power-duration + `running.critical_power` (hvis power-data tilstrekkelig) |
| 2.4 | Forbedret `weather.*` (humidity, wind) |
| 2.5 | `sleep_debt_*`, `sleep.consistency_score` |

### Fase 3 – Modell og innsikt

| # | Oppgave |
|---|---------|
| 3.1 | Utvid `performance_driver_*` med CTL, EF, decoupling |
| 3.2 | `recovery.predicted_hours_to_baseline` |
| 3.3 | Valgfritt MCP-verktøy `performance_snapshot()` – dagens kompositter + drivere i ett kall |
| 3.4 | Inkrementell backfill-jobb (historikk 5 år, idempotent) |

---

## 5. MCP-kontrakt (måltilstand)

### 5.1 Eksisterende verktøy (behold)

Coaching-verktøyene forblir hovedinngang for narrative analyse. Timeseries dekker historikk og grafer.

### 5.2 Nye / utvidede MCP-elementer (fase 1–3)

| Element | Type | Beskrivelse |
|---------|------|-------------|
| `performance_snapshot` | tool (fase 3) | Én JSON: alle kompositter + CTL/ATL/TSB + drivere for en dato |
| `treningsanalyse://daily-metrics/{date}` | resource (valgfritt) | Readiness-pakke for dato |
| Utvid `metric_catalog` | tool | `schema_version`, `ppap_phase`, grupper per kategori |
| Aliaser | catalog | f.eks. `activity.decoupling_pct` → `activity.decoupling_percent` |

### 5.3 Katalog-struktur (anbefalt)

```text
fitness.ctl | fitness.atl | fitness.tsb
fitness.ef_30d | fitness.ef_60d | fitness.ef_90d
activity.efficiency_factor | activity.decoupling_pct
running.economy_hr | running.economy_power | running.critical_speed | running.w_prime
running.fatigue_resistance_score | running.form_degradation_index
recovery.hrv_baseline | recovery.hrv_delta_pct | recovery.recovery_efficiency_score
sleep.sleep_debt_7d | sleep.consistency_score
cardio.rhr_7d | cardio.rhr_30d | cardio.hrv_*
load.* | risk.* | route.* | weather.* | training.* | predicted_* | *_score
```

Ca. **45 PPAP-nøkler** + **80+ auto-discovered** DB-felter = full dekning.

---

## 6. Tekniske prinsipper (fra PPAP, tilpasset repo)

- **Idempotent:** Backfill via `CacheCalculationService` / ny `ppap_backfill.py` – samme input gir samme output.
- **Inkrementell:** Kjør etter sync (`metrics_service`) for nye aktiviteter.
- **Manglende data:** Returner `null` i timeseries, ikke feil; flagg `data_quality` i coaching.
- **MCP stdout:** Behold `_call_tool` / `redirect_stdout` (allerede i `mcp_server.py`).
- **Ikke Delta Lake nå:** Spec nevner warehouse – vi beholder SQLite + snapshots til evt. migrering.

---

## 7. Avhengigheter og risiko

| Risiko | Mitigering |
|--------|------------|
| Doble definisjoner (Banister vs CTL) | `PpapMetricsService` som eneste kilde for MCP derived load/fitness |
| Treg MCP-query (CS, route) | Cache i `AnalyticsSnapshot`; begrens `limit` |
| Power-data sparsom | Power-metrikker `nullable`; catalog markerer `requires_power` |
| FIT-kvalitet | Gjenbruk `efficiency_data_quality` i svar |

---

## 8. Neste konkrete steg på branchen

1. ✅ Branch `cursor/nye-metrikker-0f7c` + denne planen  
2. Implementer **Fase 1.1–1.2** (`PpapMetricsService` + utvid `DERIVED_METRIC_CATALOG`)  
3. Legg til tester og oppdater README MCP-seksjon  
4. PR mot `main`; deretter Fase 2–3 i oppfølgende PR-er  

---

## 9. Oppsummering

| Kategori | Antall PPAP-nøkler (ca.) | ✅/⚠️ i dag | ❌ mangler |
|----------|--------------------------|------------|------------|
| Fitness/load | 10 | 7 | 3 (CTL/ATL/TSB som egne nøkler) |
| Aerobic / running | 12 | 5 | 7 |
| Recovery/sleep/cardio | 14 | 6 | 8 |
| Route/weather/race/training | 12 | 10 | 2 |
| Composites + driver | 9 | 7 | 2 |
| **Sum** | **~57** | **~35** | **~22** |

**Konklusjon:** Rundt **60 %** av PPAP-metrikkene finnes i backend i en eller annen form, men bare **~40 %** er eksponert med PPAP-navn via MCP. Fase 1 lukker de fleste hullene uten ny infrastruktur; Fase 2–3 dekker power, søvn og avansert modell.
