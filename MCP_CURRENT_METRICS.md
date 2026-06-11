# MCP — nåværende metrikker og ordbok

Referansedato: **2026-06-07**. Generert fra MCP-verktøyene (`metric_catalog`, `metric_glossary`, `athlete_profile`, `coaching_decision_snapshot`, `training_readiness_check`) og intern snapshot-henting som speiler `query_metric_timeseries`.

> Kjør på nytt med din lokale database: `cd backend && python3 scripts/generate_current_metrics_md.py` og `python3 scripts/generate_mcp_fresh_export.py`

---

## Sammendrag

- **Metrikker i katalog:** 404
- **Kategorier:** `acclimation`, `activity`, `aerobic_efficiency`, `cardio`, `coaching`, `fatigue`, `fitness`, `garmin_performance`, `garmin_score`, `health_hrv`, `health_recovery`, `health_sleep`, `health_stress`, `hrv`, `load_balance`, `performance`, `power`, `readiness`, `recovery`, `risk`, `route`, `running`, `running_dynamics`, `sleep`, `stamina`, `stress`, `summary`, `terrain`, `threshold`, `training`, `training_effect`, `training_load`, `training_status`, `weather`
- **Availability states:** `supported`, `computed`, `not_ingested`, `empty_source`, `unsupported`
- **Data:** 1982 aktiviteter, 1120 løp, 360 rutegrupper

---

## Viktig: ikke forveksle disse

| Tema | Metrikker | Regel |
|------|-----------|-------|
| Readiness | `readiness.total_score vs readiness_score` | readiness.total_score er Garmin-modellen (søvn 15 %, HRV 15 %, form/TSB 70 %) fra daglig-readiness. readiness_score er en intern coaching-heuristikk (recovery + Banister-form). Ikke bruk dem om hverandre. |
| Belastning | `fitness.ctl / fitness.atl / fitness.tsb vs load.acwr` | CTL/ATL/TSB beregnes fra TSS/EPOC i lokale data. load.acwr kommer fra Garmin der tilgjengelig. Begge beskriver belastning, men med ulik kilde. |
| Soner | `coaching.zone1_pct–3 vs training.class_1_pct–8` | coaching.zone* er Seiler 80/20 (lav / threshold / høy) basert på LT1/LT2. training.class_* er 8 finere klasser (recovery → race). Bruk zone* for polarisert analyse og class_* for detaljert intensitetsfordeling. |
| Duration curve | `running.speed_5m vs running.speed_5m_hist` | Uten _hist: beste verdi i nåværende snapshot (typisk all-time). Med _hist: rullerende 365-dagers beste per dag — bruk for utvikling over tid. |
| Performance driver | `performance_driver_name` | Navngir sterkest negativ faktor akkurat nå (HRV, søvn, belastning, TSB, …). Er en vektet heuristikk, ikke en Garmin-diagnose. |

---

## Kjente fallgruver (kan virke feil eller misvisende)

| Fenomen | Hva skjer | Anbefaling |
|---------|-----------|------------|
| `readiness_score` vs `readiness.total_score` | To ulike modeller (intern heuristikk vs Garmin 15/15/70) | Bruk én konsekvent |
| `fitness.tsb` og `fitness.form` | Samme beregning (alias) | Ikke tolke som to uavhengige signaler |
| `load.acwr` | Garmin ACWR hvis finnes, ellers 7d/28d TSS-ratio | Sjekk kilde før sammenligning med CTL/ATL |
| `fitness_score` / `fatigue_score` | Banister delt på 1,5, klippet 0–100 | Ikke sammenlign med rå CTL/ATL |
| `performance_score` | `50 + Banister performance` | Relativ trend, ikke absolutt skala |
| `predicted_*_time` | Critical Speed-modell | Kan avvike fra faktisk konkurranseform |
| Heuristikk (`heuristic: true`) | Modellerte coaching-score | Hint, ikke fasit |
| Ordbok uten katalog | F.eks. `consistency.score` | Se coaching snapshot nedenfor |
| `scope: activity` | Siste økt med verdi | «Per dato» = øktdato |
| `scope: snapshot` | Ofte all-time / siste beregning | Verifiser dato |

---

## Athlete profile

```json
{
  "athlete": {
    "measurement_system": "metric",
    "distance_unit": "km",
    "pace_unit": "min_per_km"
  },
  "data_inventory": {
    "activities": 1982,
    "runs": 1120,
    "route_groups": 360
  },
  "latest_threshold": {
    "observed_at": "2026-06-06T09:11:19.438085",
    "lt2_heart_rate_bpm": 164.0,
    "lt2_speed_kmh": 10.5,
    "lt2_pace_sec_per_km": 342.9,
    "lt2_pace_display": "5:43/km",
    "source": "garmin_connect",
    "validation": {
      "valid": true,
      "suspicious": false,
      "reason": null
    },
    "raw_garmin_encoding": 0.29166585,
    "raw_normalized_speed_kmh": 10.5
  },
  "latest_garmin_performance": {
    "source": "local_db",
    "availability": "supported",
    "reason": "Garmin performance-metrics fra lokal database (synk).",
    "date": "2026-06-02T00:00:00",
    "vo2_max": 44.0,
    "vo2_max_precise": 44.3,
    "training_status": 7,
    "training_status_feedback": "PRODUCTIVE_3",
    "training_balance_feedback": "AEROBIC_LOW_SHORTAGE",
    "acute_load": 607.0,
    "chronic_load": 590.0,
    "acwr_percent": 42.0,
    "endurance_score": null,
    "hill_score": null
  },
  "latest_hrv": {
    "rmssd": 32.0,
    "status": null,
    "measurement_type": "during_sleep",
    "baseline_7d": null,
    "delta_pct_vs_previous_7d": null,
    "source": "local_db",
    "live_status": "not_attempted",
    "availability": "supported",
    "reason": "HRV fra lokal database (synk fra Garmin eller parquet.)",
    "date": "2026-06-06"
  },
  "recovery_tools": {
    "daily_context": "daily_recovery_context",
    "readiness_snapshot": "readiness_snapshot",
    "coaching_check": "training_readiness_check"
  },
  "stable_context": [
    "Use metric units and min/km pace.",
    "Prefer route-matched comparisons when evaluating repeated runs.",
    "Distinguish Garmin-derived metrics from calculated coaching heuristics."
  ]
}
```

---

## Coaching decision snapshot

```json
{
  "date": "2026-06-07",
  "consistency": {
    "score": 28.6,
    "interpretation": "85+ svært bra, 70–85 bra, <60 inkonsistent"
  },
  "fitness": {
    "gain_rate_ctl_per_day": 0.35,
    "ctl": 63.5
  },
  "long_run": {
    "quality_score": null,
    "durability_score": 92.2
  },
  "readiness_by_event": {
    "5k": 46.0,
    "10k": 46.0,
    "hm": 62.7,
    "marathon": 62.7
  },
  "pb_probability": {
    "5k": 25.3,
    "10k": 25.3,
    "hm": 34.5,
    "marathon": 34.5
  },
  "polarization_score": 0.0,
  "training_block": "peak",
  "biomechanics": {
    "form_stability": 91.5
  },
  "recovery": {
    "hrv_resilience": 100.0,
    "fueling_score": null,
    "model_accuracy": null
  },
  "limiting_factors": {
    "sleep": 93.8,
    "threshold": 100.0,
    "consistency": 54.6
  },
  "top_limiter": "threshold",
  "recommended_workout": "easy_run",
  "data_gaps": [
    "fueling_score krever karbohydrat-/ernæringsregistrering",
    "recovery_model_accuracy krever historisk validering",
    "race_execution_score krever planlagt konkurransedata"
  ]
}
```

---

## Training readiness

```json
{
  "date": "2026-06-07",
  "recommendation": "normal_training",
  "banister": {
    "fitness": 60.7,
    "fatigue": 57.7,
    "performance": 3.1,
    "last_7_days_load": 253.1,
    "previous_28_days_weekly_avg_load": 477.3,
    "load_ratio_7d_to_28d_week": 0.53,
    "status": "productive_load"
  },
  "hrv_guidance": {
    "baseline_days": 60,
    "recent_days": 7,
    "rmssd_baseline": 34.9,
    "rmssd_recent": 36.3,
    "rmssd_delta_pct": 4.2,
    "resting_hr_baseline": null,
    "resting_hr_recent": 48.4,
    "resting_hr_delta_bpm": null,
    "sleep_score_recent": 89.8,
    "flags": [],
    "recommendation": "normal_training",
    "data_points": {
      "hrv": 52,
      "sleep": 6,
      "resting_hr": 5
    }
  },
  "flags": [
    "too_little_easy_volume",
    "too_much_threshold_density"
  ],
  "recovery_context": {
    "date": "2026-06-07",
    "hrv": {
      "rmssd": null,
      "status": null,
      "measurement_type": null,
      "baseline_7d": 36.0,
      "delta_pct_vs_previous_7d": null,
      "source": "none",
      "live_status": "not_attempted",
      "availability": "missing",
      "reason": "Ingen HRV registrert for aktivitetsdagen."
    },
    "sleep": {
      "total_sleep_time_s": null,
      "sleep_score": null,
      "overall_score": null,
      "sleep_efficiency": null,
      "stress_score": null,
      "recovery_score": null,
      "source": "none",
      "availability": "missing",
      "reason": "Ingen søvn registrert for dagen."
    },
    "resting_heart_rate": {
      "value": null,
      "source": "none",
      "availability": "missing",
      "reason": "Ingen hvilepuls registrert for dagen."
    },
    "stress": {
      "stress_level": null,
      "high_stress_time_s": null,
      "rest_time_s": null,
      "source": "none",
      "availability": "missing",
      "reason": "Ingen stress registrert for dagen."
    },
    "body_battery": {
      "daily_max": null,
      "daily_min": null,
      "daily_net_charge": null,
      "daily_source": "none",
      "daily_availability": "missing",
      "daily_reason": "Ingen daglig Body Battery registrert for dagen."
    },
    "training_readiness": {
      "value": 38.0,
      "readiness_status": "poor",
      "components": {
        "sleep_score": 12.9,
        "hrv_score": 55.6,
        "form_score": 39.6
      },
      "availability": "computed",
      "source": "training_readiness_service",
      "reason": "Beregnet daglig readiness fra lokal søvn/HRV/form-data."
    },
    "garmin_performance": {
      "source": "none",
      "availability": "missing",
      "reason": "Ingen Garmin performance-metrics synket for dagen."
    },
    "metric_links": {
      "hrv_timeseries": "health.hrv_rmssd",
      "readiness_timeseries": "readiness.total_score",
      "sleep_score_timeseries": "health.sleep_overall_score",
      "stress_timeseries": "health.stress_level"
    }
  },
  "readiness_composites": {
    "readiness.total_score": 38.0,
    "readiness_score": 62.5,
    "recovery_score": 82.3,
    "fitness_tsb": 7.2,
    "recovery_hrv_delta_pct": null,
    "recovery.predicted_hours_to_baseline": 36.0
  },
  "metric_links": {
    "garmin_readiness": "readiness.total_score",
    "coaching_readiness": "readiness_score",
    "hrv_raw": "health.hrv_rmssd",
    "hrv_baseline": "recovery.hrv_baseline",
    "hrv_delta": "recovery.hrv_delta_pct"
  },
  "related_tools": {
    "daily_recovery_context": "Full daglig recovery-kontekst.",
    "readiness_snapshot": "Komplette PPAP-kompositter + recovery."
  }
}
```

---

## Scope

| Scope | Betydning |
|-------|-----------|
| `activity` | Én verdi per treningsøkt. |
| `daily` | Beregnet én verdi per kalenderdag. |
| `rolling_daily` | Daglig verdi basert på rullerende vindu (f.eks. 365 dager tilbake). |
| `snapshot` | Én gjeldende verdi (typisk siste beregning / all-time). |
| `stored` | Verdi lagret i database per aktivitet eller døgn (Garmin/sync). |

---

## Kategorier

### `activity`
- Rå eller Garmin-beregnet verdi knyttet til én treningsøkt.
- *Coaching:* Bruk for konkret øktanalyse, ikke for langsiktig trend uten aggregat.

### `cardio`
- HRV, puls og aerob drift over tid.
- *Coaching:* Recovery-trend og tegn på stress/utmattelse.

### `coaching`
- Interne heuristiske scorer og drivere — ikke offisielle Garmin-score.
- *Coaching:* Suppler Garmin-data; merk alltid at det er modellert.

### `fitness`
- CTL/ATL/TSB og aerob effektivitet (EF) fra lokal TSS-modell.
- *Coaching:* Form, fitness og om athlete er fresh eller sliten.

### `performance`
- VO2, predikerte løpstider og Garmin performance-felter.
- *Coaching:* Kapasitet og målsetting — prediksjoner er modellbaserte.

### `readiness`
- Dagsform basert på søvn, HRV og treningsbalanse (Garmin-modell).
- *Coaching:* Anbefal hard / moderat / lett / hvile for dagens økt.

### `recovery`
- HRV-baseline, recovery-score og predikert tid til baseline.
- *Coaching:* Forklar hvorfor hard trening bør utsettes eller tones ned.

### `risk`
- Heuristiske risikoscore for overtrening og skade.
- *Coaching:* Advar ved høye verdier; ikke bruk som medisinsk diagnose.

### `route`
- Sammenligning med tidligere økter på samme rute.
- *Coaching:* Objektiv progresjon uavhengig av vær og dagsform.

### `running`
- Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- *Coaching:* Kapasitet, fart over varighet, og aerob effektivitet.

### `sleep`
- Søvnlengde, kvalitet og akkumulert søvngjeld.
- *Coaching:* Koble dårlig søvn til anbefalt intensitet neste dag.

### `training`
- Intensitetsfordeling og treningsklasser.
- *Coaching:* 80/20, soner og om hard trening dominerer.

### `training_load`
- Akutt/kronisk belastning og risiko for monotoni.
- *Coaching:* Vurder om volum og intensitet er bærekraftig denne uken.

### `weather`
- Temperaturjustert pace og estimert prestasjonstap.
- *Coaching:* Normaliser langsomme økter i varme/kulde.

---

## Alle metrikker med nåværende verdi

## Kategori: `acclimation`

### `performance.altitude_acclimation`

*enhet: `m` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `0` (m)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.altitude_acclimation`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «altitude_acclimation». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.heat_acclimation`

*enhet: `%` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `0` (%)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.heat_acclimation_percentage`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «heat_acclimation». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `activity`

### `activity.activity_body_battery_delta`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `-16`
- **Per dato:** `2026-06-06`
- **Availability:** Data for 29/1982 aktiviteter. Verdier kan komme fra Garmin summary eller utledes fra daglig wellness-tidsserie.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «activity_body_battery_delta». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.aerobic_training_effect_message`

*enhet: `score` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `IMPROVING_AEROBIC_ENDURANCE_9` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 531/1982 rader i `activities.aerobic_training_effect_message`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «aerobic_training_effect_message». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.anaerobic_training_effect_message`

*enhet: `score` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `NO_ANAEROBIC_BENEFIT_0` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 531/1982 rader i `activities.anaerobic_training_effect_message`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «anaerobic_training_effect_message». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.average_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `143` (bpm)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1803/1982 rader i `activities.average_heart_rate`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «average_heart_rate». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.average_moving_speed`

*enhet: `km/h` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `2.53` (km/h)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1092/1982 rader i `activities.average_moving_speed`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «average_moving_speed». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.average_pace`

*enhet: `M:SS/km` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `396.5` (M:SS/km)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1312/1982 rader i `activities.average_pace`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «average_pace». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.average_speed`

*enhet: `km/h` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `2.522` (km/h)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1335/1982 rader i `activities.average_speed`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «average_speed». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.average_speed_mps`

*enhet: `km/h` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `2.522` (km/h)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1335/1982 rader i `activities.average_speed`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «average_speed_mps». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.avg_efficiency_factor`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `0.017`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 612/1982 rader i `activities.avg_efficiency_factor`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «avg_efficiency_factor». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.cadence_drop_pct`

*enhet: `%` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `1.67` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 201/1982 rader i `activities.cadence_drop_pct`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «cadence_drop_pct». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.calories`

*enhet: `kcal` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `610` (kcal)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1912/1982 rader i `activities.calories`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «calories». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.decoupling_data_quality_score`

*enhet: `score` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `93.6` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 612/1982 rader i `activities.decoupling_data_quality_score`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «decoupling_data_quality_score». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.decoupling_reason_if_unsuitable`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `too_short`
- **Per dato:** `2026-05-18`
- **Availability:** Data lagret for 423/1982 rader i `activities.decoupling_reason_if_unsuitable`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «decoupling_reason_if_unsuitable». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.decoupling_suitability_flag`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `suitable`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 612/1982 rader i `activities.decoupling_suitability_flag`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «decoupling_suitability_flag». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.distance`

*enhet: `m` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `9468` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1981/1982 rader i `activities.distance`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «distance». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.distance_m`

*enhet: `m` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `9468` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1981/1982 rader i `activities.distance`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «distance_m». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.duration`

*enhet: `s` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `3754` (s)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1959/1982 rader i `activities.duration`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «duration». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.duration_s`

*enhet: `s` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `3754` (s)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1959/1982 rader i `activities.duration`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «duration_s». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.ef_drop_pct`

*enhet: `%` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `14.44` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 268/1982 rader i `activities.ef_drop_pct`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «ef_drop_pct». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.efficiency_data_quality`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `93.6`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 612/1982 rader i `activities.efficiency_data_quality`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «efficiency_data_quality». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.elapsed_duration`

*enhet: `s` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `3754` (s)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 910/1982 rader i `activities.elapsed_duration`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «elapsed_duration». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.grade_adjusted_pace_sec_per_km`
**Grade Adjusted Pace (GAP)**

*enhet: `M:SS/km` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `2.606` (M:SS/km)
- **Per dato:** `2026-06-06`
- **Availability:** Grade Adjusted Pace lagret for 614/1982 aktiviteter (Garmin avgGradeAdjustedSpeed når tilgjengelig, ellers FIT/Minetti; eksponert som M:SS/km).
- **Definisjon:** Garmin sin stigningsjusterte snittfart (avgGradeAdjustedSpeed), lagret som m/s i activities.avg_grade_adjusted_speed og eksponert som M:SS/km.
- **Tolkning:** Lavere pace enn rå snittfart på kupert terreng; mangler ofte på flate, innendørs eller ikke-løpsaktiviteter. Kan ikke beregnes lokalt uten Garmins modell.
- **Coaching:** Sammenlign faktisk innsats på bakke mot flat pace og terskelfart.
- **Datakilde (ordbok):** garmin_sync

### `activity.has_detailed_data`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `0`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1982/1982 rader i `activities.has_detailed_data`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «has_detailed_data». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.humidity`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `84.33`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 305/1982 rader i `activities.humidity`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «humidity». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.intensity_factor`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Intensity Factor beregnes ikke og lagres ikke i activities ennå.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «intensity_factor». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.lactate_threshold_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `164` (bpm)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 172/1982 rader i `activities.lactate_threshold_heart_rate`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «lactate_threshold_heart_rate». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.lactate_threshold_speed`

*enhet: `km/h` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `2.917` (km/h)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1539/1982 rader i `activities.lactate_threshold_speed`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «lactate_threshold_speed». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.max_elevation`

*enhet: `m` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `49.4` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 792/1982 rader i `activities.max_elevation`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «max_elevation». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.max_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `164` (bpm)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1638/1982 rader i `activities.max_heart_rate`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «max_heart_rate». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.max_power`

*enhet: `W` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `594.1` (W)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 523/1982 rader i `activities.max_power`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «max_power». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.max_running_cadence`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `186`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 520/1982 rader i `activities.max_running_cadence`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «max_running_cadence». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.max_speed`

*enhet: `km/h` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Data lagret for 729/1982 rader i `activities.max_speed`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «max_speed». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.median_efficiency_factor`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `0.018`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 612/1982 rader i `activities.median_efficiency_factor`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «median_efficiency_factor». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.min_available_stamina`

*enhet: `score` · scope: `stored` · kilde: `activities` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Min available stamina krever Garmin activity summary (minAvailableStamina). Ikke tilgjengelig i FIT/parquet; lokale rader mangler feltet fordi summary ikke returnerte verdier.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «min_available_stamina». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.min_elevation`

*enhet: `m` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `7` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 792/1982 rader i `activities.min_elevation`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «min_elevation». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.min_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `79` (bpm)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 17/1982 rader i `activities.min_heart_rate`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «min_heart_rate». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.moving_duration`

*enhet: `s` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `3742` (s)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 817/1982 rader i `activities.moving_duration`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «moving_duration». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.negative_split_percent`

*enhet: `%` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `10.04` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 879/1982 rader i `activities.negative_split_percent`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «negative_split_percent». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.pace_drop_pct`

*enhet: `%` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `13.33` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 272/1982 rader i `activities.pace_drop_pct`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «pace_drop_pct». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.pace_sec_per_km`

*enhet: `M:SS/km` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `396.5` (M:SS/km)
- **Per dato:** `2026-06-06`
- **Availability:** Forventes å få verdi når kilde- og aktivitetsdata finnes.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «pace_sec_per_km». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.recovery_time`

*enhet: `s` · scope: `stored` · kilde: `activities` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Recovery time per aktivitet finnes sjelden i Garmin activity summary (recoveryTime/timeToRecover). Ikke i FIT eller lokale parquet-filer.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «recovery_time». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.running_economy`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `6.35`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 715/1982 rader i `activities.running_economy`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «running_economy». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.steady_state_efficiency_factor`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `0.017`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 612/1982 rader i `activities.steady_state_efficiency_factor`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «steady_state_efficiency_factor». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.temperature`

*enhet: `C` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `13.92` (C)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 371/1982 rader i `activities.temperature`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «temperature». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.total_anaerobic_training_effect`

*enhet: `score` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `0` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 531/1982 rader i `activities.total_anaerobic_training_effect`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «total_anaerobic_training_effect». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.total_descent`

*enhet: `m` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `153.3` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1100/1982 rader i `activities.total_descent`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «total_descent». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.total_steps`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `1.012e+04`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 636/1982 rader i `activities.total_steps`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «total_steps». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.total_training_effect`

*enhet: `score` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `3.7` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 902/1982 rader i `activities.total_training_effect`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «total_training_effect». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.training_effect_label`

*enhet: `score` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `AEROBIC_BASE` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 531/1982 rader i `activities.training_effect_label`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «training_effect_label». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.weather_condition`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `garmin_list`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 66/1982 rader i `activities.weather_condition`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «weather_condition». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.wind_direction`

*enhet: `degrees` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `354.2` (degrees)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 329/1982 rader i `activities.wind_direction`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «wind_direction». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.wind_speed`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `0.667`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 330/1982 rader i `activities.wind_speed`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «wind_speed». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `aerobic_efficiency`

### `activity.decoupling_percent`
**Aerobic decoupling**

*enhet: `%` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `10.98` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 861/1982 rader i `activities.decoupling_percent`.
- **Definisjon:** Prosent fall i efficiency factor fra 1. til 2. halvdel av økten.
- **Tolkning:** Positiv = mer puls per fart sent i økta (aerob stress).
- **Coaching:** Kun på steady-state økter >45 min; se suitability-flagg.
- **Datakilde (ordbok):** computed_fit

### `activity.hr_drift_pct`

*enhet: `%` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `1.3` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 268/1982 rader i `activities.hr_drift_pct`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «hr_drift_pct». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `cardio`

### `cardio.drift_score`
**Cardio drift score**

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `90.8` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** 100 minus typisk HR-drift/decoupling — høyere er bedre.
- **Tolkning:** Lav score = dårlig aerob stabilitet i perioden.
- **Coaching:** Aerob kvalitet over flere økter.
- **Datakilde (ordbok):** heuristic

### `cardio.hrv_30d`

*enhet: `ms` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `36.4` (ms)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** HRV, puls og aerob drift over tid.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Recovery-trend og tegn på stress/utmattelse.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `cardio.hrv_7d`
**HRV 7-dagers snitt**

*enhet: `ms` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `36.3` (ms)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Snitt RMSSD siste 7 dager.
- **Tolkning:** Sammenlign med baseline og recovery.hrv_baseline.
- **Coaching:** Kort trend — ikke overtolking av én dag.
- **Datakilde (ordbok):** stored_hrv

### `cardio.hrv_90d`

*enhet: `ms` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `34.1` (ms)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** HRV, puls og aerob drift over tid.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Recovery-trend og tegn på stress/utmattelse.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `cardio.rhr_30d`

*enhet: `bpm` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `48.4` (bpm)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** HRV, puls og aerob drift over tid.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Recovery-trend og tegn på stress/utmattelse.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `cardio.rhr_7d`

*enhet: `bpm` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `48.4` (bpm)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** HRV, puls og aerob drift over tid.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Recovery-trend og tegn på stress/utmattelse.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

## Kategori: `coaching`

### `coaching.zone1_pct`
**Lav intensitet (soner 1)**

*enhet: `%` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `14.9` (%)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Andel økttid under LT1 (Seiler lav sone).
- **Tolkning:** Mål ~75–85 % for polarisert 80/20.
- **Coaching:** Flagg for lite rolig volum.
- **Datakilde (ordbok):** computed_lt

### `coaching.zone2_pct`
**Threshold-sone (soner 2)**

*enhet: `%` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `60.3` (%)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Andel tid mellom LT1 og LT2.
- **Tolkning:** Bør typisk være lav (<15 %) i polarisert modell.
- **Coaching:** Advar ved «grå sone»-dominans.
- **Datakilde (ordbok):** computed_lt

### `coaching.zone3_pct`
**Høy intensitet (soner 3)**

*enhet: `%` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `24.8` (%)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Andel tid over LT2.
- **Tolkning:** Noen få prosent er ofte nok; for mye øker fatigue.
- **Coaching:** Balanser med zone1_pct.
- **Datakilde (ordbok):** computed_lt

### `fatigue_score`
**Fatigue score (coaching)**

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `38.5` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Normalisert fatigue fra Banister (0–100).
- **Tolkning:** Høyere = mer akutt tretthet.
- **Coaching:** Par med fitness_score.
- **Datakilde (ordbok):** heuristic

### `fitness_score`
**Fitness score (coaching)**

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `40.5` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Normalisert Banister-fitness (0–100).
- **Tolkning:** Høyere = høyere kronisk fitness i modellen.
- **Coaching:** Forenklet fitness for narrativ.
- **Datakilde (ordbok):** heuristic

### `performance_driver_name`
**Sterkest negativ driver**

*enhet: `label` · scope: `snapshot` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `polarized_too_little_easy_volume`
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Faktornavn med høyest vektet avvik (HRV, søvn, belastning, …).
- **Tolkning:** Tekstlabel, ikke numerisk score.
- **Coaching:** Start coaching-svar med «hovedårsak akkurat nå er …»
- **Datakilde (ordbok):** heuristic_ml

### `performance_driver_weight`
**Driver-vekt**

*enhet: `ratio` · scope: `snapshot` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `0.319` (ratio)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Normalisert andel (0–1) av hvor mye den valgte driveren dominerer.
- **Tolkning:** Høyere = mer relevant å adressere først.
- **Coaching:** Prioriter tiltak etter vekt.
- **Datakilde (ordbok):** heuristic_ml

### `performance_score`
**Performance score (coaching)**

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `53.1` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Banister performance (fitness − fatigue) skalert 0–100.
- **Tolkning:** Høyere = bedre dagsform i modellen.
- **Coaching:** Dags «form» i coaching-språk.
- **Datakilde (ordbok):** heuristic

### `readiness_score`
**Coaching readiness (heuristikk)**

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `62.5` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Intern score fra recovery + Banister-form — ikke Garmin.
- **Tolkning:** 0–100, høyere = bedre dagsform i coaching-modellen.
- **Coaching:** Kun når du eksplisitt bruker coaching-modellen, ikke Garmin UI.
- **Merk:** Erstatter ikke readiness.total_score.
- **Datakilde (ordbok):** heuristic

### `recovery_score`
**Recovery score (coaching)**

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `82.3` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Sammensatt recovery fra HRV, søvn og puls.
- **Tolkning:** Høyere = bedre recovery-status.
- **Coaching:** Ikke Garmin readiness — intern.
- **Datakilde (ordbok):** heuristic

## Kategori: `fatigue`

### `activity.fatigue_resistance_score`

*enhet: `score` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `40.9` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 272/1982 rader i `activities.fatigue_resistance_score`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «fatigue_resistance_score». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `fitness`

### `fitness.atl`
**Acute Training Load (ATL)**

*enhet: `load` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `56.3` (load)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** 7-dagers eksponentiell glidende snitt av daglig TSS/EPOC.
- **Tolkning:** Reagerer raskt på nylige harde økter.
- **Coaching:** Forklar «hvor sliten er du nå» vs CTL (fitness).
- **Datakilde (ordbok):** computed_tss

### `fitness.ctl`
**Chronic Training Load (CTL)**

*enhet: `load` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `63.5` (load)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** 42-dagers eksponentiell glidende snitt av daglig TSS/EPOC.
- **Tolkning:** Høyere = mer kronisk treningsvolum (fitness). Stiger sakte.
- **Coaching:** Beskriv langsiktig treningsstatus og kapasitet.
- **Datakilde (ordbok):** computed_tss

### `fitness.ef_30d`
**Aerob effektivitet (30 dager)**

*enhet: `m_per_s_per_bpm` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `0.01729` (m_per_s_per_bpm)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Rullerende snitt av speed/HR (m/s per bpm) på rolige økter.
- **Tolkning:** Høyere = bedre økonomi ved lav intensitet over tid.
- **Coaching:** Trend for aerob utvikling — sammenlign over uker, ikke én økt.
- **Datakilde (ordbok):** computed

### `fitness.ef_60d`

*enhet: `m_per_s_per_bpm` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `0.01688` (m_per_s_per_bpm)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** CTL/ATL/TSB og aerob effektivitet (EF) fra lokal TSS-modell.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Form, fitness og om athlete er fresh eller sliten.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `fitness.ef_90d`

*enhet: `m_per_s_per_bpm` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `0.01636` (m_per_s_per_bpm)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** CTL/ATL/TSB og aerob effektivitet (EF) fra lokal TSS-modell.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Form, fitness og om athlete er fresh eller sliten.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `fitness.form`
**Form (alias TSB)**

*enhet: `load` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `7.2` (load)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Samme som fitness.tsb.
- **Tolkning:** Se fitness.tsb.
- **Coaching:** Se fitness.tsb.
- **Datakilde (ordbok):** computed_tss

### `fitness.tsb`
**Training Stress Balance (TSB / Form)**

*enhet: `load` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `7.2` (load)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** CTL minus ATL. Positiv = relativt fresh, negativ = akkumulert fatigue.
- **Tolkning:** Omtrent −10 til +10 er ofte normalt i opplæring; svært negativ = risiko.
- **Coaching:** Kjerne for taper, overreaching og restitusjonsdager.
- **Datakilde (ordbok):** computed_tss

## Kategori: `garmin_performance`

### `performance.acwr_status`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `OPTIMAL` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 392/1334 rader i `garmin_performance_metrics.acwr_status`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «acwr_status». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.acwr_status_feedback`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `FEEDBACK_2` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 392/1334 rader i `garmin_performance_metrics.acwr_status_feedback`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «acwr_status_feedback». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.altitude_trend`

*enhet: `%` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `ACCLIMATIZED` (%)
- **Per dato:** `2026-04-06`
- **Availability:** Data lagret for 32/1334 rader i `garmin_performance_metrics.altitude_trend`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «altitude_trend». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.current_altitude`

*enhet: `m` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `0` (m)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 308/1334 rader i `garmin_performance_metrics.current_altitude`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «current_altitude». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.daily_acute_chronic_workload_ratio`

*enhet: `%` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `1` (%)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 308/1334 rader i `garmin_performance_metrics.daily_acute_chronic_workload_ratio`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «daily_acute_chronic_workload_ratio». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.endurance_classification`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** raw_endurance_score er null fra Garmin metrics-service for denne kontoen.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «endurance_classification». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.fitness_age`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** fitnessAge i lagret raw_maxmet er null fra Garmin for denne kontoen (generic.fitnessAge mangler verdi i alle synkede rader).
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «fitness_age». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.fitness_trend`

*enhet: `%` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `3` (%)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.fitness_trend`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «fitness_trend». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.fitness_trend_sport`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `RUNNING`
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.fitness_trend_sport`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «fitness_trend_sport». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.heat_acclimation_percentage`

*enhet: `%` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `0` (%)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.heat_acclimation_percentage`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «heat_acclimation_percentage». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.heat_trend`

*enhet: `%` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Data lagret for 53/1334 rader i `garmin_performance_metrics.heat_trend`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «heat_trend». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.hill_endurance_score`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** raw_hill_score er null fra Garmin metrics-service for denne kontoen.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «hill_endurance_score». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.hill_strength_score`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** raw_hill_score er null fra Garmin metrics-service for denne kontoen.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «hill_strength_score». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.load_tunnel_max`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Data lagret for 75/1334 rader i `garmin_performance_metrics.load_tunnel_max`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «load_tunnel_max». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.load_tunnel_min`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Data lagret for 75/1334 rader i `garmin_performance_metrics.load_tunnel_min`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «load_tunnel_min». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.max_met_category`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `0`
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 1334/1334 rader i `garmin_performance_metrics.max_met_category`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «max_met_category». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_aerobic_high`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `2111` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.monthly_load_aerobic_high`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_aerobic_high». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_aerobic_high_target_max`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `1468` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.monthly_load_aerobic_high_target_max`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_aerobic_high_target_max». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_aerobic_high_target_min`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `816` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.monthly_load_aerobic_high_target_min`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_aerobic_high_target_min». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_aerobic_low`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `110.5` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.monthly_load_aerobic_low`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_aerobic_low». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_aerobic_low_target_max`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `1033` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.monthly_load_aerobic_low_target_max`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_aerobic_low_target_max». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_aerobic_low_target_min`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `380` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.monthly_load_aerobic_low_target_min`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_aerobic_low_target_min». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_anaerobic`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `186.7` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.monthly_load_anaerobic`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_anaerobic». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_anaerobic_target_max`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `652` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.monthly_load_anaerobic_target_max`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_anaerobic_target_max». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_anaerobic_target_min`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `217` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.monthly_load_anaerobic_target_min`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_anaerobic_target_min». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.previous_altitude_acclimation`

*enhet: `m` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `0` (m)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.previous_altitude_acclimation`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «previous_altitude_acclimation». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.previous_heat_acclimation_percentage`

*enhet: `%` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `0` (%)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.previous_heat_acclimation_percentage`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «previous_heat_acclimation_percentage». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.sport`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `RUNNING`
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 374/1334 rader i `garmin_performance_metrics.sport`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «sport». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.sub_sport`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `GENERIC`
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 374/1334 rader i `garmin_performance_metrics.sub_sport`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «sub_sport». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.training_balance_feedback_phrase`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `AEROBIC_LOW_SHORTAGE`
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.training_balance_feedback_phrase`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «training_balance_feedback_phrase». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.training_status_feedback_phrase`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `PRODUCTIVE_3` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.training_status_feedback_phrase`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «training_status_feedback_phrase». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `garmin_score`

### `performance.endurance_score`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** raw_endurance_score er null fra Garmin metrics-service for denne kontoen.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «endurance_score». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.hill_score`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** raw_hill_score er null fra Garmin metrics-service for denne kontoen.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «hill_score». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `health_hrv`

### `hrv.baseline_balanced_lower`

*enhet: `value` · scope: `stored` · kilde: `hrv` · availability: `supported`*

- **Nåværende verdi:** `31`
- **Per dato:** `2026-04-19`
- **Availability:** Data lagret for 1056/1233 rader i `hrv.baseline_balanced_lower`.
- **Definisjon:** Alias-prefix for HRV-rader i database — bruk helst health.hrv_rmssd som kanonisk nøkkel.
- **Tolkning:** Kolonne «baseline_balanced_lower». Samme kilde som health.*; se metric_aliases i metric_catalog.
- **Coaching:** Recovery-trend; foretrekk health.hrv_rmssd i timeseries.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `hrv.baseline_balanced_upper`

*enhet: `value` · scope: `stored` · kilde: `hrv` · availability: `supported`*

- **Nåværende verdi:** `40`
- **Per dato:** `2026-04-19`
- **Availability:** Data lagret for 1056/1233 rader i `hrv.baseline_balanced_upper`.
- **Definisjon:** Alias-prefix for HRV-rader i database — bruk helst health.hrv_rmssd som kanonisk nøkkel.
- **Tolkning:** Kolonne «baseline_balanced_upper». Samme kilde som health.*; se metric_aliases i metric_catalog.
- **Coaching:** Recovery-trend; foretrekk health.hrv_rmssd i timeseries.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `hrv.baseline_low_upper`

*enhet: `value` · scope: `stored` · kilde: `hrv` · availability: `supported`*

- **Nåværende verdi:** `29`
- **Per dato:** `2026-04-19`
- **Availability:** Data lagret for 1056/1233 rader i `hrv.baseline_low_upper`.
- **Definisjon:** Alias-prefix for HRV-rader i database — bruk helst health.hrv_rmssd som kanonisk nøkkel.
- **Tolkning:** Kolonne «baseline_low_upper». Samme kilde som health.*; se metric_aliases i metric_catalog.
- **Coaching:** Recovery-trend; foretrekk health.hrv_rmssd i timeseries.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `hrv.breathing_rate`

*enhet: `value` · scope: `stored` · kilde: `hrv` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kun et kjerneutvalg HRV-felt lagres i dagens sync.
- **Definisjon:** Alias-prefix for HRV-rader i database — bruk helst health.hrv_rmssd som kanonisk nøkkel.
- **Tolkning:** Kolonne «breathing_rate». Samme kilde som health.*; se metric_aliases i metric_catalog.
- **Coaching:** Recovery-trend; foretrekk health.hrv_rmssd i timeseries.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `hrv.heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `hrv` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kun et kjerneutvalg HRV-felt lagres i dagens sync.
- **Definisjon:** Alias-prefix for HRV-rader i database — bruk helst health.hrv_rmssd som kanonisk nøkkel.
- **Tolkning:** Kolonne «heart_rate». Samme kilde som health.*; se metric_aliases i metric_catalog.
- **Coaching:** Recovery-trend; foretrekk health.hrv_rmssd i timeseries.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `hrv.measurement_duration`

*enhet: `s` · scope: `stored` · kilde: `hrv` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kun et kjerneutvalg HRV-felt lagres i dagens sync.
- **Definisjon:** Alias-prefix for HRV-rader i database — bruk helst health.hrv_rmssd som kanonisk nøkkel.
- **Tolkning:** Kolonne «measurement_duration». Samme kilde som health.*; se metric_aliases i metric_catalog.
- **Coaching:** Recovery-trend; foretrekk health.hrv_rmssd i timeseries.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `hrv.measurement_quality`

*enhet: `value` · scope: `stored` · kilde: `hrv` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kun et kjerneutvalg HRV-felt lagres i dagens sync.
- **Definisjon:** Alias-prefix for HRV-rader i database — bruk helst health.hrv_rmssd som kanonisk nøkkel.
- **Tolkning:** Kolonne «measurement_quality». Samme kilde som health.*; se metric_aliases i metric_catalog.
- **Coaching:** Recovery-trend; foretrekk health.hrv_rmssd i timeseries.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `hrv.measurement_type`

*enhet: `value` · scope: `stored` · kilde: `hrv` · availability: `supported`*

- **Nåværende verdi:** `during_sleep`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1233/1233 rader i `hrv.measurement_type`.
- **Definisjon:** Alias-prefix for HRV-rader i database — bruk helst health.hrv_rmssd som kanonisk nøkkel.
- **Tolkning:** Kolonne «measurement_type». Samme kilde som health.*; se metric_aliases i metric_catalog.
- **Coaching:** Recovery-trend; foretrekk health.hrv_rmssd i timeseries.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `hrv.pnn50`

*enhet: `value` · scope: `stored` · kilde: `hrv` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kun et kjerneutvalg HRV-felt lagres i dagens sync.
- **Definisjon:** Alias-prefix for HRV-rader i database — bruk helst health.hrv_rmssd som kanonisk nøkkel.
- **Tolkning:** Kolonne «pnn50». Samme kilde som health.*; se metric_aliases i metric_catalog.
- **Coaching:** Recovery-trend; foretrekk health.hrv_rmssd i timeseries.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `hrv.rmssd`

*enhet: `value` · scope: `stored` · kilde: `hrv` · availability: `supported`*

- **Nåværende verdi:** `32`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1233/1233 rader i `hrv.rmssd`.
- **Definisjon:** Alias-prefix for HRV-rader i database — bruk helst health.hrv_rmssd som kanonisk nøkkel.
- **Tolkning:** Kolonne «rmssd». Samme kilde som health.*; se metric_aliases i metric_catalog.
- **Coaching:** Recovery-trend; foretrekk health.hrv_rmssd i timeseries.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `hrv.status`

*enhet: `score` · scope: `stored` · kilde: `hrv` · availability: `supported`*

- **Nåværende verdi:** `BALANCED` (score)
- **Per dato:** `2026-04-19`
- **Availability:** Data lagret for 1056/1233 rader i `hrv.status`.
- **Definisjon:** Alias-prefix for HRV-rader i database — bruk helst health.hrv_rmssd som kanonisk nøkkel.
- **Tolkning:** Kolonne «status». Samme kilde som health.*; se metric_aliases i metric_catalog.
- **Coaching:** Recovery-trend; foretrekk health.hrv_rmssd i timeseries.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `hrv.stress_score`

*enhet: `score` · scope: `stored` · kilde: `hrv` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kun et kjerneutvalg HRV-felt lagres i dagens sync.
- **Definisjon:** Alias-prefix for HRV-rader i database — bruk helst health.hrv_rmssd som kanonisk nøkkel.
- **Tolkning:** Kolonne «stress_score». Samme kilde som health.*; se metric_aliases i metric_catalog.
- **Coaching:** Recovery-trend; foretrekk health.hrv_rmssd i timeseries.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `health_recovery`

### `body_battery.body_battery_charged`

*enhet: `value` · scope: `stored` · kilde: `body_battery` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Charged/drained utledes fra body_battery_values_array ved sync, men tidsserien lagres ikke i DB. Eksisterende rader har kun max/min.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `body_battery.body_battery_charged_start`

*enhet: `value` · scope: `stored` · kilde: `body_battery` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Startverdier utledes fra wellness-tidsserie ved sync; tidsserie er ikke lagret i DB.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `body_battery.body_battery_drained`

*enhet: `value` · scope: `stored` · kilde: `body_battery` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Charged/drained utledes fra body_battery_values_array ved sync, men tidsserien lagres ikke i DB. Eksisterende rader har kun max/min.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `body_battery.body_battery_drained_start`

*enhet: `value` · scope: `stored` · kilde: `body_battery` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Startverdier utledes fra wellness-tidsserie ved sync; tidsserie er ikke lagret i DB.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `body_battery.max_body_battery`

*enhet: `value` · scope: `stored` · kilde: `body_battery` · availability: `supported`*

- **Nåværende verdi:** `77`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 188/188 rader i `body_battery.max_body_battery`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `body_battery.min_body_battery`

*enhet: `value` · scope: `stored` · kilde: `body_battery` · availability: `supported`*

- **Nåværende verdi:** `43`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 188/188 rader i `body_battery.min_body_battery`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `body_battery.net_charge`

*enhet: `value` · scope: `stored` · kilde: `body_battery` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Net charge krever charged/drained eller wellness-tidsserie. Eksisterende DB-rader har kun max/min uten persistert tidsserie.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `resting_heart_rate.confidence_level`

*enhet: `value` · scope: `stored` · kilde: `resting_heart_rate` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Garmin dailyHeartRate returnerer ikke confidenceLevel; feltet synkes ikke i dagens pipeline.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `resting_heart_rate.measurement_method`

*enhet: `value` · scope: `stored` · kilde: `resting_heart_rate` · availability: `supported`*

- **Nåværende verdi:** `automatic`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 5/5 rader i `resting_heart_rate.measurement_method`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `resting_heart_rate.measurement_quality`

*enhet: `value` · scope: `stored` · kilde: `resting_heart_rate` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Garmin dailyHeartRate returnerer ikke measurementQuality; feltet synkes ikke i dagens pipeline.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `resting_heart_rate.resting_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `resting_heart_rate` · availability: `supported`*

- **Nåværende verdi:** `51` (bpm)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 5/5 rader i `resting_heart_rate.resting_heart_rate`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

## Kategori: `health_sleep`

### `sleep.average_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `sleep` · availability: `empty_source`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Garmin detailed_sleep_data har nøkkel for average_heart_rate i 4/4 rader, men alle verdier er null (0/150 lagret i `sleep.average_heart_rate`).
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.average_respiration_rate`

*enhet: `value` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `13`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 4/150 rader i `sleep.average_respiration_rate`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.average_spo2`

*enhet: `value` · scope: `stored` · kilde: `sleep` · availability: `empty_source`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Garmin detailed_sleep_data har nøkkel for average_spo2 i 4/4 rader, men alle verdier er null (0/150 lagret i `sleep.average_spo2`).
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.awake_percent`

*enhet: `%` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `0.7` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 120/150 rader i `sleep.awake_percent`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.awake_time`

*enhet: `s` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `180` (s)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 120/150 rader i `sleep.awake_time`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.deep_sleep_percent`

*enhet: `%` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `19` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 120/150 rader i `sleep.deep_sleep_percent`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.deep_sleep_time`

*enhet: `s` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `5100` (s)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 120/150 rader i `sleep.deep_sleep_time`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.heart_rate_variability`

*enhet: `bpm` · scope: `stored` · kilde: `sleep` · availability: `empty_source`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kolonne `heart_rate_variability` i `sleep` har 0/150 rader med verdi. Garmin detailed_sleep_data (4 rader) mangler heart_rate_variability — krever utvidet sleep-detail-sync, ikke tilgjengelig i eksisterende lokale kilder.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.highest_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `sleep` · availability: `empty_source`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kolonne `highest_heart_rate` i `sleep` har 0/150 rader med verdi. Garmin detailed_sleep_data (4 rader) mangler highest_heart_rate — krever utvidet sleep-detail-sync, ikke tilgjengelig i eksisterende lokale kilder.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.light_sleep_percent`

*enhet: `%` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `61` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 120/150 rader i `sleep.light_sleep_percent`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.light_sleep_time`

*enhet: `s` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `1.62e+04` (s)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 120/150 rader i `sleep.light_sleep_time`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.lowest_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `sleep` · availability: `empty_source`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kolonne `lowest_heart_rate` i `sleep` har 0/150 rader med verdi. Garmin detailed_sleep_data (4 rader) mangler lowest_heart_rate — krever utvidet sleep-detail-sync, ikke tilgjengelig i eksisterende lokale kilder.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.lowest_spo2`

*enhet: `value` · scope: `stored` · kilde: `sleep` · availability: `empty_source`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Garmin detailed_sleep_data har nøkkel for lowest_spo2 i 4/4 rader, men alle verdier er null (0/150 lagret i `sleep.lowest_spo2`).
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.movement_score`

*enhet: `score` · scope: `stored` · kilde: `sleep` · availability: `empty_source`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kolonne `movement_score` i `sleep` har 0/150 rader med verdi. Garmin detailed_sleep_data (4 rader) mangler movement_score — krever utvidet sleep-detail-sync, ikke tilgjengelig i eksisterende lokale kilder.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.overall_score`

*enhet: `score` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `83` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 107/150 rader i `sleep.overall_score`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.recovery_score`

*enhet: `score` · scope: `stored` · kilde: `sleep` · availability: `empty_source`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kolonne `recovery_score` i `sleep` har 0/150 rader med verdi. Garmin detailed_sleep_data (4 rader) mangler recovery_score — krever utvidet sleep-detail-sync, ikke tilgjengelig i eksisterende lokale kilder.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.rem_sleep_percent`

*enhet: `%` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `20` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 120/150 rader i `sleep.rem_sleep_percent`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.rem_sleep_time`

*enhet: `s` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `5160` (s)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 120/150 rader i `sleep.rem_sleep_time`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.restless_moments`

*enhet: `value` · scope: `stored` · kilde: `sleep` · availability: `empty_source`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kolonne `restless_moments` i `sleep` har 0/150 rader med verdi. Garmin detailed_sleep_data (4 rader) mangler restless_moments — krever utvidet sleep-detail-sync, ikke tilgjengelig i eksisterende lokale kilder.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.sleep_efficiency`

*enhet: `value` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `99.3`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 120/150 rader i `sleep.sleep_efficiency`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.sleep_latency`

*enhet: `value` · scope: `stored` · kilde: `sleep` · availability: `empty_source`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kolonne `sleep_latency` i `sleep` har 0/150 rader med verdi. Garmin detailed_sleep_data (4 rader) mangler sleep_latency — krever utvidet sleep-detail-sync, ikke tilgjengelig i eksisterende lokale kilder.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.sleep_quality`

*enhet: `value` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `good`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 107/150 rader i `sleep.sleep_quality`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.sleep_score`

*enhet: `score` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `83` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 107/150 rader i `sleep.sleep_score`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.stress_score`

*enhet: `score` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `22` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 4/150 rader i `sleep.stress_score`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.total_sleep_time`

*enhet: `s` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `2.646e+04` (s)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 150/150 rader i `sleep.total_sleep_time`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.wake_episodes`

*enhet: `value` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `1`
- **Per dato:** `2026-06-03`
- **Availability:** Data lagret for 1/150 rader i `sleep.wake_episodes`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

## Kategori: `health_stress`

### `stress.activity_stress_duration`

*enhet: `s` · scope: `stored` · kilde: `stress` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kun stress_level og high_stress_time lagres i dagens sync.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.data_quality`

*enhet: `value` · scope: `stored` · kilde: `stress` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Kun stress_level og high_stress_time lagres i dagens sync.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.high_stress_time`

*enhet: `s` · scope: `stored` · kilde: `stress` · availability: `supported`*

- **Nåværende verdi:** `2580` (s)
- **Per dato:** `2026-06-05`
- **Availability:** Data lagret for 77/77 rader i `stress.high_stress_time`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.low_stress_time`

*enhet: `s` · scope: `stored` · kilde: `stress` · availability: `supported`*

- **Nåværende verdi:** `9000` (s)
- **Per dato:** `2026-06-05`
- **Availability:** Data lagret for 77/77 rader i `stress.low_stress_time`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.medium_stress_time`

*enhet: `s` · scope: `stored` · kilde: `stress` · availability: `supported`*

- **Nåværende verdi:** `2280` (s)
- **Per dato:** `2026-06-05`
- **Availability:** Data lagret for 77/77 rader i `stress.medium_stress_time`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.rest_time`

*enhet: `s` · scope: `stored` · kilde: `stress` · availability: `supported`*

- **Nåværende verdi:** `5.67e+04` (s)
- **Per dato:** `2026-06-05`
- **Availability:** Data lagret for 77/77 rader i `stress.rest_time`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.stress_level`

*enhet: `value` · scope: `stored` · kilde: `stress` · availability: `supported`*

- **Nåværende verdi:** `22`
- **Per dato:** `2026-06-05`
- **Availability:** Data lagret for 77/77 rader i `stress.stress_level`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.stress_time`

*enhet: `s` · scope: `stored` · kilde: `stress` · availability: `supported`*

- **Nåværende verdi:** `1.386e+04` (s)
- **Per dato:** `2026-06-05`
- **Availability:** Data lagret for 77/77 rader i `stress.stress_time`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.total_time`

*enhet: `s` · scope: `stored` · kilde: `stress` · availability: `supported`*

- **Nåværende verdi:** `7.056e+04` (s)
- **Per dato:** `2026-06-05`
- **Availability:** Data lagret for 77/77 rader i `stress.total_time`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

## Kategori: `hrv`

### `health.hrv_rmssd`
**HRV RMSSD (natt)**

*enhet: `value` · scope: `stored` · kilde: `hrv` · availability: `supported`*

- **Nåværende verdi:** `32`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1233/1233 rader i `hrv.rmssd`.
- **Definisjon:** Rå RMSSD fra siste natt-måling (ms) — kanonisk lagret HRV-nøkkel.
- **Tolkning:** Sammenlign med recovery.hrv_baseline og recovery.hrv_delta_pct for trend.
- **Coaching:** Daglig recovery; bruk cardio.hrv_7d for kort glidende snitt.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `load_balance`

### `performance.load_aerobic_high`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `2111` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.monthly_load_aerobic_high`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «load_aerobic_high». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.load_aerobic_low`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `110.5` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.monthly_load_aerobic_low`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «load_aerobic_low». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.load_anaerobic`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `186.7` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.monthly_load_anaerobic`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «load_anaerobic». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `performance`

### `activity.vo2_max`

*enhet: `ml/kg/min` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `44` (ml/kg/min)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 362/1982 rader i `activities.vo2_max`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «vo2_max». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.vo2_max_precise`

*enhet: `ml/kg/min` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `44.3` (ml/kg/min)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 1931/1982 rader i `activities.vo2_max_precise`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «vo2_max_precise». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.vo2_max`

*enhet: `ml/kg/min` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `44` (ml/kg/min)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 1334/1334 rader i `garmin_performance_metrics.vo2_max`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «vo2_max». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.vo2_max_precise`

*enhet: `ml/kg/min` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `44.3` (ml/kg/min)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 1334/1334 rader i `garmin_performance_metrics.vo2_max_precise`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «vo2_max_precise». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `predicted_10k_time`

*enhet: `s` · scope: `snapshot` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `3103` (s)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** VO2, predikerte løpstider og Garmin performance-felter.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet og målsetting — prediksjoner er modellbaserte.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `predicted_5k_time`
**Predikert 5 km-tid**

*enhet: `s` · scope: `snapshot` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `1520` (s)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Estimert tid fra CS + W′-modell.
- **Tolkning:** Sekunder — lavere er raskere.
- **Coaching:** Målsetting — kun ved god CS-modellkvalitet.
- **Datakilde (ordbok):** heuristic

### `predicted_half_marathon_time`

*enhet: `s` · scope: `snapshot` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `6618` (s)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** VO2, predikerte løpstider og Garmin performance-felter.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet og målsetting — prediksjoner er modellbaserte.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `predicted_marathon_time`

*enhet: `s` · scope: `snapshot` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `1.33e+04` (s)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** VO2, predikerte løpstider og Garmin performance-felter.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet og målsetting — prediksjoner er modellbaserte.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

## Kategori: `power`

### `activity.average_power`

*enhet: `W` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `216` (W)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 523/1982 rader i `activities.average_power`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «average_power». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.normalized_power`

*enhet: `W` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `216` (W)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 523/1982 rader i `activities.normalized_power`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «normalized_power». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `readiness`

### `activity.training_readiness_score`

*enhet: `score` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `42` (score)
- **Per dato:** `2026-04-05`
- **Availability:** Training readiness lagret for 1/1982 aktiviteter (beregnet lokalt eller fra Garmin).
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «training_readiness_score». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `readiness.form_component`
**Readiness — form (TSB)**

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `39.6` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Form/TSB normalisert til 0–100 (tung vekt i total score).
- **Tolkning:** Reflekterer CTL−ATL; lav score = høy akutt tretthet.
- **Coaching:** Koble til fitness.tsb når du forklarer belastning.
- **Datakilde (ordbok):** computed_garmin_model

### `readiness.hrv_component`
**Readiness — HRV**

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `55.6` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** HRV-komponent (0–100) basert på nylig RMSSD vs baseline.
- **Tolkning:** Lav score = autonom stress eller incomplete recovery.
- **Coaching:** Bruk sammen med recovery.hrv_delta_pct for narrativ.
- **Datakilde (ordbok):** computed_garmin_model

### `readiness.sleep_component`
**Readiness — søvn**

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `12.9` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Søvnkomponent (0–100) i Garmin readiness-modellen.
- **Tolkning:** Lav verdi tyder på utilstrekkelig eller dårlig søvn siste netter.
- **Coaching:** Forklar hvorfor rolig dag anbefales selv om athlete «føler seg ok».
- **Datakilde (ordbok):** computed_garmin_model

### `readiness.total_score`
**Garmin training readiness (total)**

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `38` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Samlet dags-score 0–100 fra TrainingReadinessService (søvn, HRV, form).
- **Tolkning:** Høyere er bedre. Under ~50: vurder lett økt. Under ~35: hvile.
- **Coaching:** Primær readiness for «kan jeg trene hardt i dag?»
- **Merk:** Ikke forveksle med readiness_score (coaching-heuristikk).
- **Datakilde (ordbok):** computed_garmin_model

## Kategori: `recovery`

### `activity.body_battery_delta`
**Body Battery endring (aktivitet)**

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `-16`
- **Per dato:** `2026-06-06`
- **Availability:** Data for 29/1982 aktiviteter. Verdier kan komme fra Garmin summary eller utledes fra daglig wellness-tidsserie.
- **Definisjon:** Endring i Body Battery gjennom aktiviteten (summaryDTO.differenceBodyBattery).
- **Tolkning:** Negativ = tap; positiv = netto lading under økta (sjeldent ved hard trening).
- **Coaching:** Koble belastning til recovery-kostnad samme dag.
- **Merk:** Samme kolonne som activity.activity_body_battery_delta.
- **Datakilde (ordbok):** garmin_sync

### `activity.body_battery_start`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `67`
- **Per dato:** `2026-06-06`
- **Availability:** Data for 29/1982 aktiviteter. Verdier kan komme fra Garmin summary eller utledes fra daglig wellness-tidsserie.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «body_battery_start». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `health.body_battery_max`

*enhet: `value` · scope: `stored` · kilde: `body_battery` · availability: `supported`*

- **Nåværende verdi:** `77`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 188/188 rader i `body_battery.max_body_battery`.
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «body_battery_max». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `health.body_battery_min`

*enhet: `value` · scope: `stored` · kilde: `body_battery` · availability: `supported`*

- **Nåværende verdi:** `43`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 188/188 rader i `body_battery.min_body_battery`.
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «body_battery_min». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `health.body_battery_net_charge`

*enhet: `value` · scope: `stored` · kilde: `body_battery` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Net charge krever charged/drained fra wellness-tidsserie. Eksisterende DB-rader har kun max/min; tidsserie ble ikke persistert ved sync.
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «body_battery_net_charge». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `health.resting_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `resting_heart_rate` · availability: `supported`*

- **Nåværende verdi:** `51` (bpm)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 5/5 rader i `resting_heart_rate.resting_heart_rate`.
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «resting_heart_rate». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `recovery.hrv_baseline`

*enhet: `ms` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `36` (ms)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** HRV-baseline, recovery-score og predikert tid til baseline.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Forklar hvorfor hard trening bør utsettes eller tones ned.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `recovery.hrv_delta_pct`
**HRV avvik fra baseline (%)**

*enhet: `%` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `-11.11` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Prosentvis avvik RMSSD vs 28-dagers baseline.
- **Tolkning:** Negativ = under normal — ofte tegn på stress/fatigue.
- **Coaching:** Forklar readiness og hvile anbefaling.
- **Datakilde (ordbok):** computed

### `recovery.predicted_hours_to_baseline`
**Predikert timer til baseline**

*enhet: `hours` · scope: `daily` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `36` (hours)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Heuristisk estimat (6–120 t) før readiness/TSB normaliseres.
- **Tolkning:** Høyere = mer hvile anbefales før hard økt.
- **Coaching:** Konkret «vent X timer» — merk at det er estimat, ikke Garmin.
- **Merk:** PPAP fase 3-heuristikk, ikke klinisk validert.
- **Datakilde (ordbok):** heuristic

### `recovery.recovery_efficiency_score`

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `82.3` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** HRV-baseline, recovery-score og predikert tid til baseline.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Forklar hvorfor hard trening bør utsettes eller tones ned.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

## Kategori: `risk`

### `injury_risk_score`
**Skaderisiko (heuristikk)**

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `7` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Kombinasjon av ACWR, monotoni og overtraining.
- **Tolkning:** 0–100, høyere = mer risiko.
- **Coaching:** Advar — ikke medisinsk prognose.
- **Datakilde (ordbok):** heuristic

### `overtraining_score`
**Overtreningsscore**

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `11.5` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Heuristikk fra belastning, form og HRV-flagg.
- **Tolkning:** Høyere = større risiko for overreaching.
- **Coaching:** Foreslå lett uke eller hvile.
- **Datakilde (ordbok):** heuristic

### `risk.overtraining_score`
**Overtreningsrisiko (alias)**

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `11.5` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Samme konsept som overtraining_score.
- **Tolkning:** Se overtraining_score.
- **Datakilde (ordbok):** heuristic

## Kategori: `route`

### `route.hr_delta_pct`

*enhet: `%` · scope: `activity` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `-6.57` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Sammenligning med tidligere økter på samme rute.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Objektiv progresjon uavhengig av vær og dagsform.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `route.performance_delta_pct`

*enhet: `%` · scope: `activity` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `9.06` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Sammenligning med tidligere økter på samme rute.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Objektiv progresjon uavhengig av vær og dagsform.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `route.power_delta_pct`

*enhet: `%` · scope: `activity` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `-18.36` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Sammenligning med tidligere økter på samme rute.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Objektiv progresjon uavhengig av vær og dagsform.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `route_fingerprint.bbox_max_latitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `59.96`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.bbox_max_latitude`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.bbox_max_longitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `10.65`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.bbox_max_longitude`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.bbox_min_latitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `59.94`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.bbox_min_latitude`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.bbox_min_longitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `10.64`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.bbox_min_longitude`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.centroid_latitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `59.95`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.centroid_latitude`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.centroid_longitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `10.65`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.centroid_longitude`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.end_latitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `59.94`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.end_latitude`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.end_longitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `10.64`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.end_longitude`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.gps_point_count`

*enhet: `count` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `2976` (count)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.gps_point_count`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.method_version`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `route-match-v1`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.method_version`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.point_count`

*enhet: `count` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `2984` (count)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.point_count`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.quality_score`

*enhet: `score` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `1` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.quality_score`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.route_distance_m`

*enhet: `m` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `7337` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.route_distance_m`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.sampled_point_count`

*enhet: `count` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `100` (count)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.sampled_point_count`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.start_latitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `59.94`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.start_latitude`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.start_longitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints` · availability: `supported`*

- **Nåværende verdi:** `10.64`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 733/733 rader i `activity_route_fingerprints.start_longitude`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.distance_ratio`

*enhet: `%` · scope: `stored` · kilde: `activity_route_matches` · availability: `supported`*

- **Nåværende verdi:** `0.225` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 268278/268278 rader i `activity_route_matches.distance_ratio`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.end_distance_m`

*enhet: `m` · scope: `stored` · kilde: `activity_route_matches` · availability: `supported`*

- **Nåværende verdi:** `4.234e+04` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 268278/268278 rader i `activity_route_matches.end_distance_m`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.mean_distance_m`

*enhet: `m` · scope: `stored` · kilde: `activity_route_matches` · availability: `supported`*

- **Nåværende verdi:** `4.495e+04` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 268278/268278 rader i `activity_route_matches.mean_distance_m`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.method_version`

*enhet: `value` · scope: `stored` · kilde: `activity_route_matches` · availability: `supported`*

- **Nåværende verdi:** `route-match-v1`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 268278/268278 rader i `activity_route_matches.method_version`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.overlap_quality`

*enhet: `value` · scope: `stored` · kilde: `activity_route_matches` · availability: `supported`*

- **Nåværende verdi:** `0`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 268278/268278 rader i `activity_route_matches.overlap_quality`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.p90_distance_m`

*enhet: `m` · scope: `stored` · kilde: `activity_route_matches` · availability: `supported`*

- **Nåværende verdi:** `4.739e+04` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 268278/268278 rader i `activity_route_matches.p90_distance_m`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.reverse_direction`

*enhet: `degrees` · scope: `stored` · kilde: `activity_route_matches` · availability: `supported`*

- **Nåværende verdi:** `0` (degrees)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 268278/268278 rader i `activity_route_matches.reverse_direction`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.same_route`

*enhet: `value` · scope: `stored` · kilde: `activity_route_matches` · availability: `supported`*

- **Nåværende verdi:** `0`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 268278/268278 rader i `activity_route_matches.same_route`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.similarity_score`

*enhet: `score` · scope: `stored` · kilde: `activity_route_matches` · availability: `supported`*

- **Nåværende verdi:** `0` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 268278/268278 rader i `activity_route_matches.similarity_score`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.start_distance_m`

*enhet: `m` · scope: `stored` · kilde: `activity_route_matches` · availability: `supported`*

- **Nåværende verdi:** `4.232e+04` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 268278/268278 rader i `activity_route_matches.start_distance_m`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

## Kategori: `running`

### `running.critical_power`

*enhet: `W` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `running.critical_speed`
**Critical Speed**

*enhet: `km/h` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `3.158` (km/h)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** CS fra hyperbolsk modell (m/s) på beste speed-efforts siste ~365 d.
- **Tolkning:** Høyere = bedre aerob/anaerob kapasitet.
- **Coaching:** Kapasitet og pacing for intervaller.
- **Datakilde (ordbok):** computed_fit

### `running.economy_hr`

*enhet: `ratio` · scope: `activity` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `0.01764` (ratio)
- **Per dato:** `2026-06-06`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `running.economy_power`

*enhet: `ratio` · scope: `activity` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `0.01168` (ratio)
- **Per dato:** `2026-06-06`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `running.form_degradation_index`

*enhet: `score` · scope: `activity` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `59.2` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `running.power_10m`
**Beste 10 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig effekt over 10 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_10m_hist`
**Beste 10 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste effekt over 10 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_1m`
**Beste 1 minutt effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig effekt over 1 minutt i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_1m_hist`
**Beste 1 minutt effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste effekt over 1 minutt fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_20m`
**Beste 20 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig effekt over 20 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_20m_hist`
**Beste 20 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste effekt over 20 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_30s`
**Beste 30 sekunder effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig effekt over 30 sekunder i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_30s_hist`
**Beste 30 sekunder effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste effekt over 30 sekunder fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_3m`
**Beste 3 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig effekt over 3 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_3m_hist`
**Beste 3 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste effekt over 3 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_40m`
**Beste 40 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig effekt over 40 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_40m_hist`
**Beste 40 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste effekt over 40 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_5m`
**Beste 5 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig effekt over 5 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_5m_hist`
**Beste 5 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste effekt over 5 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_60m`
**Beste 60 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig effekt over 60 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_60m_hist`
**Beste 60 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste effekt over 60 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_10m`
**Beste 10 minutter fart (snapshot)**

*enhet: `km/h` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `4.945` (km/h)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig fart over 10 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_10m_hist`
**Beste 10 minutter fart (365d rullerende)**

*enhet: `km/h` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste fart over 10 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_1m`
**Beste 1 minutt fart (snapshot)**

*enhet: `km/h` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `8.115` (km/h)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig fart over 1 minutt i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_1m_hist`
**Beste 1 minutt fart (365d rullerende)**

*enhet: `km/h` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste fart over 1 minutt fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_20m`
**Beste 20 minutter fart (snapshot)**

*enhet: `km/h` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `4.213` (km/h)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig fart over 20 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_20m_hist`
**Beste 20 minutter fart (365d rullerende)**

*enhet: `km/h` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste fart over 20 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_30s`
**Beste 30 sekunder fart (snapshot)**

*enhet: `km/h` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `9.262` (km/h)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig fart over 30 sekunder i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_30s_hist`
**Beste 30 sekunder fart (365d rullerende)**

*enhet: `km/h` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste fart over 30 sekunder fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_3m`
**Beste 3 minutter fart (snapshot)**

*enhet: `km/h` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `6.185` (km/h)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig fart over 3 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_3m_hist`
**Beste 3 minutter fart (365d rullerende)**

*enhet: `km/h` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste fart over 3 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_40m`
**Beste 40 minutter fart (snapshot)**

*enhet: `km/h` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `3.665` (km/h)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig fart over 40 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_40m_hist`
**Beste 40 minutter fart (365d rullerende)**

*enhet: `km/h` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste fart over 40 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_5m`
**Beste 5 minutter fart (snapshot)**

*enhet: `km/h` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `5.517` (km/h)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig fart over 5 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_5m_hist`
**Beste 5 minutter fart (365d rullerende)**

*enhet: `km/h` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste fart over 5 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_60m`
**Beste 60 minutter fart (snapshot)**

*enhet: `km/h` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `3.192` (km/h)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Beste gjennomsnittlig fart over 60 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_60m_hist`
**Beste 60 minutter fart (365d rullerende)**

*enhet: `km/h` · scope: `rolling_daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Per dag: beste fart over 60 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.w_prime`
**W′ (anaerob kapasitet)**

*enhet: `m` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `200.5` (m)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Skjærepunkt D′ fra CS-modell (meter).
- **Tolkning:** Større W′ = mer «kick» over CS.
- **Coaching:** Forklar kort, hard innsats vs lang distanse.
- **Datakilde (ordbok):** computed_fit

### `running.w_prime_power`

*enhet: `W` · scope: `snapshot` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** *(ingen verdi)*
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

## Kategori: `running_dynamics`

### `activity.average_running_cadence`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `162.7`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 645/1982 rader i `activities.average_running_cadence`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «average_running_cadence». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.ground_contact_time`

*enhet: `ms` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `293.4` (ms)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 492/1982 rader i `activities.ground_contact_time`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «ground_contact_time». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.stride_length`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `0.929`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 572/1982 rader i `activities.stride_length`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «stride_length». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.vertical_oscillation`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `8.29`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 492/1982 rader i `activities.vertical_oscillation`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «vertical_oscillation». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.vertical_ratio`

*enhet: `%` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `8.74` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 422/1982 rader i `activities.vertical_ratio`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «vertical_ratio». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `sleep`

### `health.sleep_duration_s`

*enhet: `s` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `2.646e+04` (s)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 150/150 rader i `sleep.total_sleep_time`.
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «sleep_duration_s». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `health.sleep_overall_score`

*enhet: `score` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `83` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 107/150 rader i `sleep.overall_score`.
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «sleep_overall_score». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `health.sleep_score`

*enhet: `score` · scope: `stored` · kilde: `sleep` · availability: `supported`*

- **Nåværende verdi:** `83` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 107/150 rader i `sleep.sleep_score`.
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «sleep_score». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `sleep.consistency_score`

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `94.4` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Søvnlengde, kvalitet og akkumulert søvngjeld.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Koble dårlig søvn til anbefalt intensitet neste dag.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `sleep.sleep_debt_14d`

*enhet: `hours` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `2.89` (hours)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Søvnlengde, kvalitet og akkumulert søvngjeld.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Koble dårlig søvn til anbefalt intensitet neste dag.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `sleep.sleep_debt_28d`

*enhet: `hours` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `5.18` (hours)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Søvnlengde, kvalitet og akkumulert søvngjeld.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Koble dårlig søvn til anbefalt intensitet neste dag.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `sleep.sleep_debt_7d`
**Søvngjeld 7 dager**

*enhet: `hours` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `1.15` (hours)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Akkumulert timer under 8t søvn per natt.
- **Tolkning:** Høyere = mer uoppgjort søvn.
- **Coaching:** Forklar trøtthet uten hard trening.
- **Datakilde (ordbok):** computed

## Kategori: `stamina`

### `activity.begin_potential_stamina`

*enhet: `score` · scope: `stored` · kilde: `activities` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Potential stamina krever Garmin activity summary (beginPotentialStamina). Ikke tilgjengelig i FIT/parquet; lokale rader mangler feltet fordi summary ikke returnerte verdier.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «begin_potential_stamina». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.end_potential_stamina`

*enhet: `score` · scope: `stored` · kilde: `activities` · availability: `not_ingested`*

- **Nåværende verdi:** *(ingen verdi)*
- **Availability:** Potential stamina krever Garmin activity summary (endPotentialStamina). Ikke tilgjengelig i FIT/parquet; lokale rader mangler feltet fordi summary ikke returnerte verdier.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «end_potential_stamina». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `stress`

### `health.high_stress_time_s`

*enhet: `s` · scope: `stored` · kilde: `stress` · availability: `supported`*

- **Nåværende verdi:** `2580` (s)
- **Per dato:** `2026-06-05`
- **Availability:** Data lagret for 77/77 rader i `stress.high_stress_time`.
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «high_stress_time_s». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `health.stress_level`

*enhet: `value` · scope: `stored` · kilde: `stress` · availability: `supported`*

- **Nåværende verdi:** `22`
- **Per dato:** `2026-06-05`
- **Availability:** Data lagret for 77/77 rader i `stress.stress_level`.
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «stress_level». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `summary`

### `daily_summary.avg_cadence`

*enhet: `value` · scope: `stored` · kilde: `daily_summaries` · availability: `supported`*

- **Nåværende verdi:** `162.7`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 623/1314 rader i `daily_summaries.avg_cadence`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.avg_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `daily_summaries` · availability: `supported`*

- **Nåværende verdi:** `143` (bpm)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1237/1314 rader i `daily_summaries.avg_heart_rate`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.avg_pace`

*enhet: `M:SS/km` · scope: `stored` · kilde: `daily_summaries` · availability: `supported`*

- **Nåværende verdi:** `396.5` (M:SS/km)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1083/1314 rader i `daily_summaries.avg_pace`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.avg_speed`

*enhet: `km/h` · scope: `stored` · kilde: `daily_summaries` · availability: `supported`*

- **Nåværende verdi:** `2.522` (km/h)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1083/1314 rader i `daily_summaries.avg_speed`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.best_distance`

*enhet: `m` · scope: `stored` · kilde: `daily_summaries` · availability: `supported`*

- **Nåværende verdi:** `9468` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1314/1314 rader i `daily_summaries.best_distance`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.best_duration`

*enhet: `s` · scope: `stored` · kilde: `daily_summaries` · availability: `supported`*

- **Nåværende verdi:** `3754` (s)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1314/1314 rader i `daily_summaries.best_duration`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.best_pace`

*enhet: `M:SS/km` · scope: `stored` · kilde: `daily_summaries` · availability: `supported`*

- **Nåværende verdi:** `396.5` (M:SS/km)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1081/1314 rader i `daily_summaries.best_pace`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.best_speed`

*enhet: `km/h` · scope: `stored` · kilde: `daily_summaries` · availability: `supported`*

- **Nåværende verdi:** `2.522` (km/h)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1314/1314 rader i `daily_summaries.best_speed`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.total_activities`

*enhet: `value` · scope: `stored` · kilde: `daily_summaries` · availability: `supported`*

- **Nåværende verdi:** `1`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1314/1314 rader i `daily_summaries.total_activities`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.total_ascent`

*enhet: `m` · scope: `stored` · kilde: `daily_summaries` · availability: `supported`*

- **Nåværende verdi:** `155.8` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1314/1314 rader i `daily_summaries.total_ascent`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.total_calories`

*enhet: `kcal` · scope: `stored` · kilde: `daily_summaries` · availability: `supported`*

- **Nåværende verdi:** `610` (kcal)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1314/1314 rader i `daily_summaries.total_calories`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.total_descent`

*enhet: `m` · scope: `stored` · kilde: `daily_summaries` · availability: `supported`*

- **Nåværende verdi:** `153.3` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1314/1314 rader i `daily_summaries.total_descent`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.total_distance`

*enhet: `m` · scope: `stored` · kilde: `daily_summaries` · availability: `supported`*

- **Nåværende verdi:** `9468` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1314/1314 rader i `daily_summaries.total_distance`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.total_duration`

*enhet: `s` · scope: `stored` · kilde: `daily_summaries` · availability: `supported`*

- **Nåværende verdi:** `3754` (s)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1314/1314 rader i `daily_summaries.total_duration`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.activities_per_day`

*enhet: `value` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `0.067`
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.activities_per_day`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.activities_per_week`

*enhet: `value` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `0.467`
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.activities_per_week`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.activities_trend`

*enhet: `%` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `-80` (%)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 148/166 rader i `monthly_summaries.activities_trend`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.avg_cadence`

*enhet: `value` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `161.3`
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 97/166 rader i `monthly_summaries.avg_cadence`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.avg_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `142.5` (bpm)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 160/166 rader i `monthly_summaries.avg_heart_rate`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.avg_pace`

*enhet: `M:SS/km` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `400.9` (M:SS/km)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 161/166 rader i `monthly_summaries.avg_pace`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.avg_speed`

*enhet: `km/h` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `2.495` (km/h)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 161/166 rader i `monthly_summaries.avg_speed`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.best_distance`

*enhet: `m` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `9468` (m)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.best_distance`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.best_duration`

*enhet: `s` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `3754` (s)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.best_duration`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.best_pace`

*enhet: `M:SS/km` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `396.5` (M:SS/km)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 161/166 rader i `monthly_summaries.best_pace`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.best_speed`

*enhet: `km/h` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `2.522` (km/h)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.best_speed`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.distance_per_day`

*enhet: `m` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `560.2` (m)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.distance_per_day`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.distance_per_week`

*enhet: `m` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `3921` (m)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.distance_per_week`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.distance_trend`

*enhet: `%` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `-77.71` (%)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 143/166 rader i `monthly_summaries.distance_trend`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.duration_per_day`

*enhet: `s` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `224.6` (s)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.duration_per_day`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.duration_per_week`

*enhet: `s` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `1572` (s)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.duration_per_week`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.duration_trend`

*enhet: `%` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `-74.77` (%)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 148/166 rader i `monthly_summaries.duration_trend`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.month`

*enhet: `count` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `6` (count)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.month`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.total_activities`

*enhet: `value` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `2`
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.total_activities`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.total_ascent`

*enhet: `m` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `274` (m)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.total_ascent`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.total_calories`

*enhet: `kcal` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `1084` (kcal)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.total_calories`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.total_descent`

*enhet: `m` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `266.9` (m)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.total_descent`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.total_distance`

*enhet: `m` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `1.68e+04` (m)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.total_distance`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.total_duration`

*enhet: `s` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `6737` (s)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.total_duration`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.total_tss`

*enhet: `value` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `253.1`
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.total_tss`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.year`

*enhet: `count` · scope: `stored` · kilde: `monthly_summaries` · availability: `supported`*

- **Nåværende verdi:** `2026` (count)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 166/166 rader i `monthly_summaries.year`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.activities_per_day`

*enhet: `value` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `0.286`
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 577/577 rader i `weekly_summaries.activities_per_day`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.avg_cadence`

*enhet: `value` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `161.3`
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 319/577 rader i `weekly_summaries.avg_cadence`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.avg_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `142.5` (bpm)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 563/577 rader i `weekly_summaries.avg_heart_rate`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.avg_pace`

*enhet: `M:SS/km` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `400.9` (M:SS/km)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 516/577 rader i `weekly_summaries.avg_pace`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.avg_speed`

*enhet: `km/h` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `2.495` (km/h)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 516/577 rader i `weekly_summaries.avg_speed`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.best_distance`

*enhet: `m` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `9468` (m)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 577/577 rader i `weekly_summaries.best_distance`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.best_duration`

*enhet: `s` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `3754` (s)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 577/577 rader i `weekly_summaries.best_duration`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.best_pace`

*enhet: `M:SS/km` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `396.5` (M:SS/km)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 509/577 rader i `weekly_summaries.best_pace`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.best_speed`

*enhet: `km/h` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `2.522` (km/h)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 577/577 rader i `weekly_summaries.best_speed`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.distance_per_day`

*enhet: `m` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `2401` (m)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 577/577 rader i `weekly_summaries.distance_per_day`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.duration_per_day`

*enhet: `s` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `962.4` (s)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 577/577 rader i `weekly_summaries.duration_per_day`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.total_activities`

*enhet: `value` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `2`
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 577/577 rader i `weekly_summaries.total_activities`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.total_ascent`

*enhet: `m` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `274` (m)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 577/577 rader i `weekly_summaries.total_ascent`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.total_calories`

*enhet: `kcal` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `1084` (kcal)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 577/577 rader i `weekly_summaries.total_calories`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.total_descent`

*enhet: `m` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `266.9` (m)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 577/577 rader i `weekly_summaries.total_descent`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.total_distance`

*enhet: `m` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `1.68e+04` (m)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 577/577 rader i `weekly_summaries.total_distance`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.total_duration`

*enhet: `s` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `6737` (s)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 577/577 rader i `weekly_summaries.total_duration`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.week_number`

*enhet: `count` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `23` (count)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 577/577 rader i `weekly_summaries.week_number`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.year`

*enhet: `count` · scope: `stored` · kilde: `weekly_summaries` · availability: `supported`*

- **Nåværende verdi:** `2026` (count)
- **Per dato:** `2026-06-01`
- **Availability:** Data lagret for 577/577 rader i `weekly_summaries.year`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.activities_per_day`

*enhet: `value` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `0.096`
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.activities_per_day`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.activities_per_month`

*enhet: `value` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `2.917`
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.activities_per_month`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.activities_per_week`

*enhet: `value` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `0.671`
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.activities_per_week`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.activities_trend`

*enhet: `%` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `-63.54` (%)
- **Per dato:** `2026`
- **Availability:** Data lagret for 18/19 rader i `yearly_summaries.activities_trend`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.avg_cadence`

*enhet: `value` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `158.7`
- **Per dato:** `2026`
- **Availability:** Data lagret for 14/19 rader i `yearly_summaries.avg_cadence`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.avg_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `147.8` (bpm)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.avg_heart_rate`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.avg_pace`

*enhet: `M:SS/km` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `367.3` (M:SS/km)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.avg_pace`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.avg_speed`

*enhet: `km/h` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `2.722` (km/h)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.avg_speed`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.best_distance`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `6.065e+04` (m)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.best_distance`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.best_duration`

*enhet: `s` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `1.792e+04` (s)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.best_duration`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.best_pace`

*enhet: `M:SS/km` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `295.4` (M:SS/km)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.best_pace`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.best_speed`

*enhet: `km/h` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `3.385` (km/h)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.best_speed`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.distance_per_day`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `851.1` (m)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.distance_per_day`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.distance_per_month`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `2.589e+04` (m)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.distance_per_month`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.distance_per_week`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `5958` (m)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.distance_per_week`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.distance_trend`

*enhet: `%` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `-60.09` (%)
- **Per dato:** `2026`
- **Availability:** Data lagret for 18/19 rader i `yearly_summaries.distance_trend`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.duration_per_day`

*enhet: `s` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `312.6` (s)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.duration_per_day`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.duration_per_month`

*enhet: `s` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `9509` (s)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.duration_per_month`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.duration_per_week`

*enhet: `s` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `2188` (s)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.duration_per_week`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.duration_trend`

*enhet: `%` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `-55.8` (%)
- **Per dato:** `2026`
- **Availability:** Data lagret for 18/19 rader i `yearly_summaries.duration_trend`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.total_activities`

*enhet: `value` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `35`
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.total_activities`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.total_ascent`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `8578` (m)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.total_ascent`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.total_calories`

*enhet: `kcal` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `1.655e+04` (kcal)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.total_calories`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.total_descent`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `8472` (m)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.total_descent`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.total_distance`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `3.106e+05` (m)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.total_distance`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.total_duration`

*enhet: `s` · scope: `stored` · kilde: `yearly_summaries` · availability: `supported`*

- **Nåværende verdi:** `1.141e+05` (s)
- **Per dato:** `2026`
- **Availability:** Data lagret for 19/19 rader i `yearly_summaries.total_duration`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

## Kategori: `terrain`

### `activity.total_ascent`

*enhet: `m` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `155.8` (m)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 1096/1982 rader i `activities.total_ascent`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «total_ascent». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `threshold`

### `lactate_threshold.is_fallback`

*enhet: `value` · scope: `stored` · kilde: `lactate_threshold_history` · availability: `supported`*

- **Nåværende verdi:** `0`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 38/38 rader i `lactate_threshold_history.is_fallback`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `lactate_threshold.lactate_threshold_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `lactate_threshold_history` · availability: `supported`*

- **Nåværende verdi:** `164` (bpm)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 38/38 rader i `lactate_threshold_history.lactate_threshold_heart_rate`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `lactate_threshold.lactate_threshold_speed`

*enhet: `km/h` · scope: `stored` · kilde: `lactate_threshold_history` · availability: `supported`*

- **Nåværende verdi:** `2.917` (km/h)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 37/38 rader i `lactate_threshold_history.lactate_threshold_speed`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `lactate_threshold.raw_lactate_threshold_speed`

*enhet: `internal` · scope: `stored` · kilde: `lactate_threshold_history` · availability: `supported`*

- **Nåværende verdi:** `0.292` (internal)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 38/38 rader i `lactate_threshold_history.raw_lactate_threshold_speed`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `lactate_threshold.source`

*enhet: `value` · scope: `stored` · kilde: `lactate_threshold_history` · availability: `supported`*

- **Nåværende verdi:** `garmin_connect`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 38/38 rader i `lactate_threshold_history.source`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `lactate_threshold.sync_context`

*enhet: `value` · scope: `stored` · kilde: `lactate_threshold_history` · availability: `supported`*

- **Nåværende verdi:** `activity_sync`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 38/38 rader i `lactate_threshold_history.sync_context`.
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

## Kategori: `training`

### `training.aerobic_score`

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `92.2` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Intensitetsfordeling og treningsklasser.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** 80/20, soner og om hard trening dominerer.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `training.anaerobic_score`

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `7.8` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Intensitetsfordeling og treningsklasser.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** 80/20, soner og om hard trening dominerer.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `training.class_1_pct`
**Treningsklasse 1 (Recovery) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `0` (%)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Andel økttid klassifisert som Recovery siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.class_2_pct`
**Treningsklasse 2 (Lett) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `0` (%)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Andel økttid klassifisert som Lett siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.class_3_pct`
**Treningsklasse 3 (Aerob) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `37` (%)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Andel økttid klassifisert som Aerob siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.class_4_pct`
**Treningsklasse 4 (Tempo) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `25.5` (%)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Andel økttid klassifisert som Tempo siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.class_5_pct`
**Treningsklasse 5 (Threshold) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `24.9` (%)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Andel økttid klassifisert som Threshold siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.class_6_pct`
**Treningsklasse 6 (VO2) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `12.6` (%)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Andel økttid klassifisert som VO2 siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.class_7_pct`
**Treningsklasse 7 (Anaerob) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `0` (%)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Andel økttid klassifisert som Anaerob siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.class_8_pct`
**Treningsklasse 8 (Race) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `0` (%)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Andel økttid klassifisert som Race siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.training_class`
**8-klassers sone (per økt)**

*enhet: `class` · scope: `activity` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `3`
- **Per dato:** `2026-06-06`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** 1=recovery … 8=race, basert på puls vs LT1/LT2.
- **Tolkning:** Hele tall 1–8.
- **Coaching:** Detaljert intensitet på enkeltøkter.
- **Datakilde (ordbok):** computed_lt

### `training.training_zone`
**3-sones sone (per økt)**

*enhet: `zone` · scope: `activity` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `2`
- **Per dato:** `2026-06-06`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** 1=under LT1, 2=mellom LT1–LT2, 3=over LT2 (snittpuls).
- **Tolkning:** Grov klassifisering per aktivitet.
- **Coaching:** Rask øktklassifisering — bruk class_* for finfordeling.
- **Datakilde (ordbok):** computed_lt

## Kategori: `training_effect`

### `activity.aerobic_training_effect`

*enhet: `score` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `3.7` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 902/1982 rader i `activities.total_training_effect`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «aerobic_training_effect». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.anaerobic_training_effect`

*enhet: `score` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `0` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 531/1982 rader i `activities.total_anaerobic_training_effect`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «anaerobic_training_effect». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `training_load`

### `activity.epoc`

*enhet: `value` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `142.6`
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 531/1982 rader i `activities.epoc`.
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «epoc». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.training_stress_score`
**Training Stress Score (TSS)**

*enhet: `score` · scope: `stored` · kilde: `activities` · availability: `supported`*

- **Nåværende verdi:** `142.6` (score)
- **Per dato:** `2026-06-06`
- **Availability:** Data lagret for 912/1982 rader i `activities.training_stress_score`.
- **Definisjon:** Belastningsscore per økt (≈ EPOC fra Garmin der tilgjengelig).
- **Tolkning:** 100 ≈ 1 time ved terskel; summeres til CTL/ATL.
- **Coaching:** Volum og intensitet per uke.
- **Datakilde (ordbok):** garmin_or_estimated

### `load.acwr`
**Acute:Chronic Workload Ratio**

*enhet: `ratio` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `1` (ratio)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Akutt/kronisk belastningsforhold (Garmin eller coaching-fallback).
- **Tolkning:** ~0.8–1.3 ofte trygt; >1.5 øker skaderisiko i litteraturen.
- **Coaching:** Advar ved brå økning i belastning.
- **Datakilde (ordbok):** garmin_or_computed

### `load.monotony`
**Treningsmonotoni**

*enhet: `ratio` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `0.63` (ratio)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Snitt belastning / standardavvik siste 7 dager.
- **Tolkning:** Høy monotoni = lite variasjon dag til dag.
- **Coaching:** Anbefal variasjon eller hviledag ved høy monotoni + høy strain.
- **Datakilde (ordbok):** computed

### `load.strain`
**Treningsstrain**

*enhet: `score` · scope: `daily` · kilde: `derived` · availability: `computed`*

- **Nåværende verdi:** `158.3` (score)
- **Per dato:** `2026-06-07`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Ukes sum TSS multiplisert med monotoni.
- **Tolkning:** Høy strain = mye volum med lite variasjon.
- **Coaching:** Kombiner med monotony for overtreningssignal.
- **Datakilde (ordbok):** computed

### `performance.acwr_percent`

*enhet: `%` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `42` (%)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 392/1334 rader i `garmin_performance_metrics.acwr_percent`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «acwr_percent». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.daily_training_load_acute`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `607` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 392/1334 rader i `garmin_performance_metrics.daily_training_load_acute`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «daily_training_load_acute». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.daily_training_load_chronic`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `590` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 392/1334 rader i `garmin_performance_metrics.daily_training_load_chronic`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «daily_training_load_chronic». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `training_status`

### `performance.training_status`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics` · availability: `supported`*

- **Nåværende verdi:** `7` (score)
- **Per dato:** `2026-06-02`
- **Availability:** Data lagret for 467/1334 rader i `garmin_performance_metrics.training_status`.
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «training_status». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `weather`

### `weather.adjusted_pace`

*enhet: `M:SS/km` · scope: `activity` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `405` (M:SS/km)
- **Per dato:** `2026-06-06`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Temperaturjustert pace og estimert prestasjonstap.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Normaliser langsomme økter i varme/kulde.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `weather.performance_penalty_pct`

*enhet: `%` · scope: `activity` · kilde: `derived` · availability: `computed` · **heuristikk***

- **Nåværende verdi:** `2.15` (%)
- **Per dato:** `2026-06-06`
- **Availability:** Beregnes lokalt fra eksisterende trenings-, helse- eller snapshot-data.
- **Definisjon:** Temperaturjustert pace og estimert prestasjonstap.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Normaliser langsomme økter i varme/kulde.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

---

## Ordbok uten katalogoppføring

15 nøkler i ordbok som ikke er i `metric_catalog`. 6 har beregnet verdi i dag.

### `activity.body_battery_delta`
**Body Battery endring (aktivitet)**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Endring i Body Battery gjennom aktiviteten (summaryDTO.differenceBodyBattery).
- **Tolkning:** Negativ = tap; positiv = netto lading under økta (sjeldent ved hard trening).
- **Coaching:** Koble belastning til recovery-kostnad samme dag.
- **Merk:** Samme kolonne som activity.activity_body_battery_delta.
- **Datakilde (ordbok):** garmin_sync

### `activity.decoupling_percent`
**Aerobic decoupling**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Prosent fall i efficiency factor fra 1. til 2. halvdel av økten.
- **Tolkning:** Positiv = mer puls per fart sent i økta (aerob stress).
- **Coaching:** Kun på steady-state økter >45 min; se suitability-flagg.
- **Datakilde (ordbok):** computed_fit

### `activity.grade_adjusted_pace_sec_per_km`
**Grade Adjusted Pace (GAP)**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin sin stigningsjusterte snittfart (avgGradeAdjustedSpeed), lagret som m/s i activities.avg_grade_adjusted_speed og eksponert som M:SS/km.
- **Tolkning:** Lavere pace enn rå snittfart på kupert terreng; mangler ofte på flate, innendørs eller ikke-løpsaktiviteter. Kan ikke beregnes lokalt uten Garmins modell.
- **Coaching:** Sammenlign faktisk innsats på bakke mot flat pace og terskelfart.
- **Datakilde (ordbok):** garmin_sync

### `activity.training_stress_score`
**Training Stress Score (TSS)**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Belastningsscore per økt (≈ EPOC fra Garmin der tilgjengelig).
- **Tolkning:** 100 ≈ 1 time ved terskel; summeres til CTL/ATL.
- **Coaching:** Volum og intensitet per uke.
- **Datakilde (ordbok):** garmin_or_estimated

### `coaching.polarization_score`
**Polarization score**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `0`
- **Per dato:** `2026-06-07`
- **Definisjon:** Hvor nær 80/20-fordeling (lav/høy) brukeren er.
- **Tolkning:** 100 = ideell polarisert profil siste 28 dager.
- **Coaching:** Juster volum mot rolig vs hard trening.
- **Datakilde (ordbok):** computed

### `coaching.recommended_workout`
**Anbefalt neste økt**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `easy_run`
- **Per dato:** `2026-06-07`
- **Definisjon:** Enum: rest, recovery_run, easy_run, threshold, vo2_intervals, long_run, …
- **Tolkning:** Samlet anbefaling fra readiness, belastning og treningsfase.
- **Coaching:** Konkret «hva bør du gjøre i dag».
- **Datakilde (ordbok):** heuristic

### `consistency.score`
**Training Consistency Score**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `28.6`
- **Per dato:** `2026-06-07`
- **Definisjon:** Andel av siste 28 dager med minst én løpeøkt (0–100).
- **Tolkning:** 85+ svært bra, 70–85 bra, under 60 inkonsistent.
- **Coaching:** Vurder om fremgang stoppes av hull i treningen, ikke bare CTL.
- **Datakilde (ordbok):** computed

### `fitness.gain_rate`
**Fitness gain rate (CTL)**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `0.35`
- **Per dato:** `2026-06-07`
- **Definisjon:** Endring i CTL per dag over siste 42 dager.
- **Tolkning:** Positiv = bygger form; negativ = taper eller sykdom.
- **Coaching:** Retning viktigere enn dagens CTL-nivå.
- **Datakilde (ordbok):** computed

### `health.hrv_rmssd`
**HRV RMSSD (natt)**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Rå RMSSD fra siste natt-måling (ms) — kanonisk lagret HRV-nøkkel.
- **Tolkning:** Sammenlign med recovery.hrv_baseline og recovery.hrv_delta_pct for trend.
- **Coaching:** Daglig recovery; bruk cardio.hrv_7d for kort glidende snitt.
- **Datakilde (ordbok):** garmin_sync

### `readiness.5k`
**Event readiness 5K**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `46`
- **Per dato:** `2026-06-07`
- **Definisjon:** Konkurransespesifikk readiness 0–100 for 5 km.
- **Tolkning:** Kombinerer Garmin readiness, TSB, HRV og søvn for kort race.
- **Coaching:** Anbefal start eller utsettelse av 5K/10K.
- **Datakilde (ordbok):** heuristic

### `running.durability_score`
**Durability score**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `92.2`
- **Per dato:** `2026-06-07`
- **Definisjon:** Evnen til å holde prestasjon på langkjøringer (drift, fatigue resistance).
- **Tolkning:** Høyere = bedre utholdenhet sent i lange økter.
- **Coaching:** Maraton/HM-planlegging og langtur-kvalitet.
- **Datakilde (ordbok):** computed

### `running.power_30m`
**Beste 30 minutter effekt (snapshot)**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig effekt over 30 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_30m_hist`
**Beste 30 minutter effekt (365d rullerende)**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste effekt over 30 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_30m`
**Beste 30 minutter fart (snapshot)**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig fart over 30 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_30m_hist`
**Beste 30 minutter fart (365d rullerende)**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste fart over 30 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

---

## Statistikk

- Med verdi: **337** / 404
- Uten verdi: **67**
