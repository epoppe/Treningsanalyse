# MCP — nåværende metrikker og ordbok

Referansedato: **2026-05-31**. Generert fra MCP-verktøyene (`metric_catalog`, `metric_glossary`, `athlete_profile`, `coaching_decision_snapshot`, `training_readiness_check`) og intern snapshot-henting som speiler `query_metric_timeseries`.

> Kjør på nytt med din lokale database: `cd backend && python3 scripts/generate_current_metrics_md.py`

---

## Sammendrag

- **Metrikker i katalog:** 404
- **Kategorier:** `acclimation`, `activity`, `aerobic_efficiency`, `cardio`, `coaching`, `fatigue`, `fitness`, `garmin_performance`, `garmin_score`, `health_hrv`, `health_recovery`, `health_sleep`, `health_stress`, `hrv`, `load_balance`, `performance`, `power`, `readiness`, `recovery`, `risk`, `route`, `running`, `running_dynamics`, `sleep`, `stamina`, `stress`, `summary`, `terrain`, `threshold`, `training`, `training_effect`, `training_load`, `training_status`, `weather`
- **Data:** 0 aktiviteter, 0 løp, 0 rutegrupper

### Observasjoner for denne kjøringen

- **17** metrikker har verdi uten aktiviteter i databasen — sannsynligvis standardverdier/heuristikk, ikke målt data.
- Consistency score er **0.0** (0 treningsdager), men limiter `consistency` er **97.5** — høy limiter-score betyr «sterk begrensning», ikke god konsistens.
- Event readiness (5k/10k/HM/maraton) har tall uten treningsdata — `get_event_readiness` faller tilbake til `total_score=50` når Garmin-readiness mangler.
- Training block er **peak** med CTL/ATL/TSB ≈ 0 — `get_training_block` tolker null-belastning som «peak»-grensetilfelle.
- Training readiness anbefaler **normal_training** uten HRV-baseline — manglende data gir ofte «grønt lys» i stedet for «ukjent».
- Banister-status er **productive_load** med fitness/fatigue 0 — status-tekst kan være misvisende ved tom historikk.
- Bare **17/404** metrikker har verdi — forvent mange «ingen verdi»-felt; sjekk sync og at metrics er precomputet.


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
    "activities": 0,
    "runs": 0,
    "route_groups": 0
  },
  "latest_threshold": {
    "observed_at": null,
    "lt2_heart_rate_bpm": null,
    "lt2_speed_mps": null,
    "lt2_pace_sec_per_km": null,
    "source": null
  },
  "latest_garmin_performance": {},
  "latest_hrv": {
    "date": null,
    "rmssd": null,
    "status": null
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
  "date": "2026-05-31",
  "consistency": {
    "score": 0.0,
    "interpretation": "85+ svært bra, 70–85 bra, <60 inkonsistent"
  },
  "fitness": {
    "gain_rate_ctl_per_day": 0.0,
    "ctl": 0.0
  },
  "long_run": {
    "quality_score": null,
    "durability_score": null
  },
  "readiness_by_event": {
    "5k": 58.0,
    "10k": 58.0,
    "hm": 55.0,
    "marathon": 50.0
  },
  "pb_probability": {
    "5k": 31.9,
    "10k": 31.9,
    "hm": 30.2,
    "marathon": 27.5
  },
  "polarization_score": null,
  "training_block": "peak",
  "biomechanics": {
    "form_stability": null
  },
  "recovery": {
    "hrv_resilience": null,
    "fueling_score": null,
    "model_accuracy": null
  },
  "limiting_factors": {
    "sleep": 27.0,
    "consistency": 97.5
  },
  "top_limiter": "consistency",
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
  "date": "2026-05-31",
  "recommendation": "normal_training",
  "banister": {
    "fitness": 0.0,
    "fatigue": 0.0,
    "performance": 0.0,
    "last_7_days_load": 0.0,
    "previous_28_days_weekly_avg_load": 0,
    "load_ratio_7d_to_28d_week": null,
    "status": "productive_load"
  },
  "hrv_guidance": {
    "baseline_days": 60,
    "recent_days": 7,
    "rmssd_baseline": null,
    "rmssd_recent": null,
    "rmssd_delta_pct": null,
    "resting_hr_baseline": null,
    "resting_hr_recent": null,
    "resting_hr_delta_bpm": null,
    "sleep_score_recent": null,
    "flags": [],
    "recommendation": "normal_training",
    "data_points": {
      "hrv": 0,
      "sleep": 0,
      "resting_hr": 0
    }
  },
  "flags": [
    "missing_lt2_heart_rate"
  ]
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

*enhet: `m` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «altitude_acclimation». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.heat_acclimation`

*enhet: `%` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «heat_acclimation». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `activity`

### `activity.activity_body_battery_delta`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «activity_body_battery_delta». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.aerobic_training_effect_message`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «aerobic_training_effect_message». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.anaerobic_training_effect_message`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «anaerobic_training_effect_message». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.average_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «average_heart_rate». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.average_moving_speed`

*enhet: `m/s` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «average_moving_speed». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.average_pace`

*enhet: `s/km` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «average_pace». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.average_speed`

*enhet: `m/s` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «average_speed». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.average_speed_mps`

*enhet: `m/s` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «average_speed_mps». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.avg_efficiency_factor`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «avg_efficiency_factor». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.avg_grade_adjusted_speed`

*enhet: `m/s` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «avg_grade_adjusted_speed». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.body_battery_start`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «body_battery_start». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.cadence_drop_pct`

*enhet: `%` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «cadence_drop_pct». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.calories`

*enhet: `kcal` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «calories». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.decoupling_data_quality_score`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «decoupling_data_quality_score». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.decoupling_reason_if_unsuitable`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «decoupling_reason_if_unsuitable». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.decoupling_suitability_flag`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «decoupling_suitability_flag». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.distance`

*enhet: `m` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «distance». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.distance_m`

*enhet: `m` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «distance_m». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.duration`

*enhet: `%` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «duration». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.duration_s`

*enhet: `s` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «duration_s». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.ef_drop_pct`

*enhet: `%` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «ef_drop_pct». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.efficiency_data_quality`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «efficiency_data_quality». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.elapsed_duration`

*enhet: `%` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «elapsed_duration». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.grade_adjusted_speed_mps`

*enhet: `m/s` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «grade_adjusted_speed_mps». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.ground_contact_time`

*enhet: `s` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «ground_contact_time». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.has_detailed_data`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «has_detailed_data». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.humidity`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «humidity». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.intensity_factor`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «intensity_factor». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.lactate_threshold_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «lactate_threshold_heart_rate». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.lactate_threshold_speed`

*enhet: `m/s` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «lactate_threshold_speed». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.max_elevation`

*enhet: `m` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «max_elevation». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.max_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «max_heart_rate». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.max_power`

*enhet: `W` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «max_power». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.max_running_cadence`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «max_running_cadence». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.max_speed`

*enhet: `m/s` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «max_speed». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.median_efficiency_factor`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «median_efficiency_factor». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.min_available_stamina`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «min_available_stamina». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.min_elevation`

*enhet: `m` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «min_elevation». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.min_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «min_heart_rate». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.moving_duration`

*enhet: `%` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «moving_duration». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.negative_split_percent`

*enhet: `%` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «negative_split_percent». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.pace_drop_pct`

*enhet: `%` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «pace_drop_pct». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.pace_sec_per_km`

*enhet: `s/km` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «pace_sec_per_km». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.recovery_time`

*enhet: `s` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «recovery_time». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.running_economy`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «running_economy». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.steady_state_efficiency_factor`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «steady_state_efficiency_factor». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.temperature`

*enhet: `C` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «temperature». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.total_anaerobic_training_effect`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «total_anaerobic_training_effect». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.total_descent`

*enhet: `m` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «total_descent». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.total_steps`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «total_steps». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.total_training_effect`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «total_training_effect». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.training_effect_label`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «training_effect_label». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.weather_condition`

*enhet: `value` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «weather_condition». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.wind_speed`

*enhet: `m/s` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «wind_speed». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `aerobic_efficiency`

### `activity.decoupling_percent`
**Aerobic decoupling**

*enhet: `%` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Prosent fall i efficiency factor fra 1. til 2. halvdel av økten.
- **Tolkning:** Positiv = mer puls per fart sent i økta (aerob stress).
- **Coaching:** Kun på steady-state økter >45 min; se suitability-flagg.
- **Datakilde (ordbok):** computed_fit

### `activity.hr_drift_pct`

*enhet: `%` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «hr_drift_pct». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `cardio`

### `cardio.drift_score`
**Cardio drift score**

*enhet: `score` · scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** 100 minus typisk HR-drift/decoupling — høyere er bedre.
- **Tolkning:** Lav score = dårlig aerob stabilitet i perioden.
- **Coaching:** Aerob kvalitet over flere økter.
- **Datakilde (ordbok):** heuristic

### `cardio.hrv_30d`

*enhet: `ms` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** HRV, puls og aerob drift over tid.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Recovery-trend og tegn på stress/utmattelse.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `cardio.hrv_7d`
**HRV 7-dagers snitt**

*enhet: `ms` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Snitt RMSSD siste 7 dager.
- **Tolkning:** Sammenlign med baseline og recovery.hrv_baseline.
- **Coaching:** Kort trend — ikke overtolking av én dag.
- **Datakilde (ordbok):** stored_hrv

### `cardio.hrv_90d`

*enhet: `ms` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** HRV, puls og aerob drift over tid.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Recovery-trend og tegn på stress/utmattelse.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `cardio.rhr_30d`

*enhet: `bpm` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** HRV, puls og aerob drift over tid.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Recovery-trend og tegn på stress/utmattelse.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `cardio.rhr_7d`

*enhet: `bpm` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** HRV, puls og aerob drift over tid.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Recovery-trend og tegn på stress/utmattelse.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

## Kategori: `coaching`

### `coaching.zone1_pct`
**Lav intensitet (soner 1)**

*enhet: `%` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Andel økttid under LT1 (Seiler lav sone).
- **Tolkning:** Mål ~75–85 % for polarisert 80/20.
- **Coaching:** Flagg for lite rolig volum.
- **Datakilde (ordbok):** computed_lt

### `coaching.zone2_pct`
**Threshold-sone (soner 2)**

*enhet: `%` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Andel tid mellom LT1 og LT2.
- **Tolkning:** Bør typisk være lav (<15 %) i polarisert modell.
- **Coaching:** Advar ved «grå sone»-dominans.
- **Datakilde (ordbok):** computed_lt

### `coaching.zone3_pct`
**Høy intensitet (soner 3)**

*enhet: `%` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Andel tid over LT2.
- **Tolkning:** Noen få prosent er ofte nok; for mye øker fatigue.
- **Coaching:** Balanser med zone1_pct.
- **Datakilde (ordbok):** computed_lt

### `fatigue_score`
**Fatigue score (coaching)**

*enhet: `score` · scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `` (score)
- **Per dato:** `2026-05-31`
- **Definisjon:** Normalisert fatigue fra Banister (0–100).
- **Tolkning:** Høyere = mer akutt tretthet.
- **Coaching:** Par med fitness_score.
- **Datakilde (ordbok):** heuristic

### `fitness_score`
**Fitness score (coaching)**

*enhet: `score` · scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `` (score)
- **Per dato:** `2026-05-31`
- **Definisjon:** Normalisert Banister-fitness (0–100).
- **Tolkning:** Høyere = høyere kronisk fitness i modellen.
- **Coaching:** Forenklet fitness for narrativ.
- **Datakilde (ordbok):** heuristic

### `performance_driver_name`
**Sterkest negativ driver**

*enhet: `label` · scope: `snapshot` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `form_balance`
- **Per dato:** `2026-05-31`
- **Definisjon:** Faktornavn med høyest vektet avvik (HRV, søvn, belastning, …).
- **Tolkning:** Tekstlabel, ikke numerisk score.
- **Coaching:** Start coaching-svar med «hovedårsak akkurat nå er …»
- **Datakilde (ordbok):** heuristic_ml

### `performance_driver_weight`
**Driver-vekt**

*enhet: `ratio` · scope: `snapshot` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Per dato:** `2026-05-31`
- **Definisjon:** Normalisert andel (0–1) av hvor mye den valgte driveren dominerer.
- **Tolkning:** Høyere = mer relevant å adressere først.
- **Coaching:** Prioriter tiltak etter vekt.
- **Datakilde (ordbok):** heuristic_ml

### `performance_score`
**Performance score (coaching)**

*enhet: `score` · scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `5` (score)
- **Per dato:** `2026-05-31`
- **Definisjon:** Banister performance (fitness − fatigue) skalert 0–100.
- **Tolkning:** Høyere = bedre dagsform i modellen.
- **Coaching:** Dags «form» i coaching-språk.
- **Datakilde (ordbok):** heuristic

### `readiness_score`
**Coaching readiness (heuristikk)**

*enhet: `score` · scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `37.5` (score)
- **Per dato:** `2026-05-31`
- **Definisjon:** Intern score fra recovery + Banister-form — ikke Garmin.
- **Tolkning:** 0–100, høyere = bedre dagsform i coaching-modellen.
- **Coaching:** Kun når du eksplisitt bruker coaching-modellen, ikke Garmin UI.
- **Merk:** Erstatter ikke readiness.total_score.
- **Datakilde (ordbok):** heuristic

### `recovery_score`
**Recovery score (coaching)**

*enhet: `score` · scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Sammensatt recovery fra HRV, søvn og puls.
- **Tolkning:** Høyere = bedre recovery-status.
- **Coaching:** Ikke Garmin readiness — intern.
- **Datakilde (ordbok):** heuristic

## Kategori: `fatigue`

### `activity.fatigue_resistance_score`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «fatigue_resistance_score». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `fitness`

### `fitness.atl`
**Acute Training Load (ATL)**

*enhet: `load` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** `` (load)
- **Per dato:** `2026-05-31`
- **Definisjon:** 7-dagers eksponentiell glidende snitt av daglig TSS/EPOC.
- **Tolkning:** Reagerer raskt på nylige harde økter.
- **Coaching:** Forklar «hvor sliten er du nå» vs CTL (fitness).
- **Datakilde (ordbok):** computed_tss

### `fitness.ctl`
**Chronic Training Load (CTL)**

*enhet: `load` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** `` (load)
- **Per dato:** `2026-05-31`
- **Definisjon:** 42-dagers eksponentiell glidende snitt av daglig TSS/EPOC.
- **Tolkning:** Høyere = mer kronisk treningsvolum (fitness). Stiger sakte.
- **Coaching:** Beskriv langsiktig treningsstatus og kapasitet.
- **Datakilde (ordbok):** computed_tss

### `fitness.ef_30d`
**Aerob effektivitet (30 dager)**

*enhet: `m_per_s_per_bpm` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Rullerende snitt av speed/HR (m/s per bpm) på rolige økter.
- **Tolkning:** Høyere = bedre økonomi ved lav intensitet over tid.
- **Coaching:** Trend for aerob utvikling — sammenlign over uker, ikke én økt.
- **Datakilde (ordbok):** computed

### `fitness.ef_60d`

*enhet: `m_per_s_per_bpm` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** CTL/ATL/TSB og aerob effektivitet (EF) fra lokal TSS-modell.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Form, fitness og om athlete er fresh eller sliten.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `fitness.ef_90d`

*enhet: `m_per_s_per_bpm` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** CTL/ATL/TSB og aerob effektivitet (EF) fra lokal TSS-modell.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Form, fitness og om athlete er fresh eller sliten.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `fitness.form`
**Form (alias TSB)**

*enhet: `load` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** `` (load)
- **Per dato:** `2026-05-31`
- **Definisjon:** Samme som fitness.tsb.
- **Tolkning:** Se fitness.tsb.
- **Coaching:** Se fitness.tsb.
- **Datakilde (ordbok):** computed_tss

### `fitness.tsb`
**Training Stress Balance (TSB / Form)**

*enhet: `load` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** `` (load)
- **Per dato:** `2026-05-31`
- **Definisjon:** CTL minus ATL. Positiv = relativt fresh, negativ = akkumulert fatigue.
- **Tolkning:** Omtrent −10 til +10 er ofte normalt i opplæring; svært negativ = risiko.
- **Coaching:** Kjerne for taper, overreaching og restitusjonsdager.
- **Datakilde (ordbok):** computed_tss

## Kategori: `garmin_performance`

### `performance.acwr_status`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «acwr_status». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.acwr_status_feedback`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «acwr_status_feedback». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.altitude_trend`

*enhet: `m` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «altitude_trend». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.current_altitude`

*enhet: `m` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «current_altitude». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.daily_acute_chronic_workload_ratio`

*enhet: `%` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «daily_acute_chronic_workload_ratio». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.endurance_classification`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «endurance_classification». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.fitness_age`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «fitness_age». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.fitness_trend`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «fitness_trend». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.fitness_trend_sport`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «fitness_trend_sport». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.heat_acclimation_percentage`

*enhet: `%` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «heat_acclimation_percentage». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.heat_trend`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «heat_trend». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.hill_endurance_score`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «hill_endurance_score». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.hill_strength_score`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «hill_strength_score». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.load_tunnel_max`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «load_tunnel_max». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.load_tunnel_min`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «load_tunnel_min». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.max_met_category`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «max_met_category». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_aerobic_high`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_aerobic_high». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_aerobic_high_target_max`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_aerobic_high_target_max». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_aerobic_high_target_min`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_aerobic_high_target_min». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_aerobic_low`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_aerobic_low». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_aerobic_low_target_max`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_aerobic_low_target_max». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_aerobic_low_target_min`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_aerobic_low_target_min». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_anaerobic`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_anaerobic». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_anaerobic_target_max`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_anaerobic_target_max». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.monthly_load_anaerobic_target_min`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «monthly_load_anaerobic_target_min». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.previous_altitude_acclimation`

*enhet: `m` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «previous_altitude_acclimation». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.previous_heat_acclimation_percentage`

*enhet: `%` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «previous_heat_acclimation_percentage». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.sport`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «sport». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.sub_sport`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «sub_sport». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.training_balance_feedback_phrase`

*enhet: `value` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «training_balance_feedback_phrase». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.training_status_feedback_phrase`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «training_status_feedback_phrase». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `garmin_score`

### `performance.endurance_score`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «endurance_score». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.hill_score`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «hill_score». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `health_hrv`

### `hrv.baseline_balanced_lower`

*enhet: `value` · scope: `stored` · kilde: `hrv`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `hrv.baseline_balanced_upper`

*enhet: `value` · scope: `stored` · kilde: `hrv`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `hrv.baseline_low_upper`

*enhet: `value` · scope: `stored` · kilde: `hrv`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `hrv.breathing_rate`

*enhet: `value` · scope: `stored` · kilde: `hrv`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `hrv.heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `hrv`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `hrv.measurement_duration`

*enhet: `%` · scope: `stored` · kilde: `hrv`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `hrv.measurement_quality`

*enhet: `value` · scope: `stored` · kilde: `hrv`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `hrv.measurement_type`

*enhet: `value` · scope: `stored` · kilde: `hrv`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `hrv.pnn50`

*enhet: `value` · scope: `stored` · kilde: `hrv`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `hrv.rmssd`

*enhet: `value` · scope: `stored` · kilde: `hrv`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `hrv.status`

*enhet: `score` · scope: `stored` · kilde: `hrv`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `hrv.stress_score`

*enhet: `score` · scope: `stored` · kilde: `hrv`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

## Kategori: `health_recovery`

### `body_battery.body_battery_charged`

*enhet: `value` · scope: `stored` · kilde: `body_battery`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `body_battery.body_battery_charged_start`

*enhet: `value` · scope: `stored` · kilde: `body_battery`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `body_battery.body_battery_drained`

*enhet: `value` · scope: `stored` · kilde: `body_battery`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `body_battery.body_battery_drained_start`

*enhet: `value` · scope: `stored` · kilde: `body_battery`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `body_battery.max_body_battery`

*enhet: `value` · scope: `stored` · kilde: `body_battery`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `body_battery.min_body_battery`

*enhet: `value` · scope: `stored` · kilde: `body_battery`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `body_battery.net_charge`

*enhet: `value` · scope: `stored` · kilde: `body_battery`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `resting_heart_rate.confidence_level`

*enhet: `value` · scope: `stored` · kilde: `resting_heart_rate`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `resting_heart_rate.measurement_method`

*enhet: `value` · scope: `stored` · kilde: `resting_heart_rate`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `resting_heart_rate.measurement_quality`

*enhet: `value` · scope: `stored` · kilde: `resting_heart_rate`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `resting_heart_rate.resting_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `resting_heart_rate`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

## Kategori: `health_sleep`

### `sleep.average_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.average_respiration_rate`

*enhet: `%` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.average_spo2`

*enhet: `value` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.awake_percent`

*enhet: `%` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.awake_time`

*enhet: `s` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.deep_sleep_percent`

*enhet: `%` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.deep_sleep_time`

*enhet: `s` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.heart_rate_variability`

*enhet: `bpm` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.highest_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.light_sleep_percent`

*enhet: `%` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.light_sleep_time`

*enhet: `s` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.lowest_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.lowest_spo2`

*enhet: `value` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.movement_score`

*enhet: `score` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.overall_score`

*enhet: `score` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.recovery_score`

*enhet: `score` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.rem_sleep_percent`

*enhet: `%` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.rem_sleep_time`

*enhet: `s` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.restless_moments`

*enhet: `value` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.sleep_efficiency`

*enhet: `value` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.sleep_latency`

*enhet: `value` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.sleep_quality`

*enhet: `value` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.sleep_score`

*enhet: `score` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.stress_score`

*enhet: `score` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.total_sleep_time`

*enhet: `s` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `sleep.wake_episodes`

*enhet: `value` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

## Kategori: `health_stress`

### `stress.activity_stress_duration`

*enhet: `%` · scope: `stored` · kilde: `stress`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.data_quality`

*enhet: `value` · scope: `stored` · kilde: `stress`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.high_stress_time`

*enhet: `s` · scope: `stored` · kilde: `stress`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.low_stress_time`

*enhet: `s` · scope: `stored` · kilde: `stress`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.medium_stress_time`

*enhet: `s` · scope: `stored` · kilde: `stress`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.rest_time`

*enhet: `s` · scope: `stored` · kilde: `stress`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.stress_level`

*enhet: `value` · scope: `stored` · kilde: `stress`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.stress_time`

*enhet: `s` · scope: `stored` · kilde: `stress`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `stress.total_time`

*enhet: `s` · scope: `stored` · kilde: `stress`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

## Kategori: `hrv`

### `health.hrv_rmssd`

*enhet: `ms` · scope: `stored` · kilde: `hrv`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «hrv_rmssd». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `load_balance`

### `performance.load_aerobic_high`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «load_aerobic_high». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.load_aerobic_low`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «load_aerobic_low». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.load_anaerobic`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «load_anaerobic». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `performance`

### `activity.vo2_max`

*enhet: `ml/kg/min` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «vo2_max». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.vo2_max_precise`

*enhet: `ml/kg/min` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «vo2_max_precise». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.vo2_max`

*enhet: `ml/kg/min` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «vo2_max». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.vo2_max_precise`

*enhet: `ml/kg/min` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «vo2_max_precise». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `predicted_10k_time`

*enhet: `s` · scope: `snapshot` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** VO2, predikerte løpstider og Garmin performance-felter.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet og målsetting — prediksjoner er modellbaserte.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `predicted_5k_time`
**Predikert 5 km-tid**

*enhet: `s` · scope: `snapshot` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Estimert tid fra CS + W′-modell.
- **Tolkning:** Sekunder — lavere er raskere.
- **Coaching:** Målsetting — kun ved god CS-modellkvalitet.
- **Datakilde (ordbok):** heuristic

### `predicted_half_marathon_time`

*enhet: `s` · scope: `snapshot` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** VO2, predikerte løpstider og Garmin performance-felter.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet og målsetting — prediksjoner er modellbaserte.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `predicted_marathon_time`

*enhet: `s` · scope: `snapshot` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** VO2, predikerte løpstider og Garmin performance-felter.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet og målsetting — prediksjoner er modellbaserte.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

## Kategori: `power`

### `activity.average_power`

*enhet: `W` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «average_power». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.normalized_power`

*enhet: `W` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «normalized_power». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `readiness`

### `activity.training_readiness_score`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «training_readiness_score». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `readiness.form_component`
**Readiness — form (TSB)**

*enhet: `score` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** `5` (score)
- **Per dato:** `2026-05-31`
- **Definisjon:** Form/TSB normalisert til 0–100 (tung vekt i total score).
- **Tolkning:** Reflekterer CTL−ATL; lav score = høy akutt tretthet.
- **Coaching:** Koble til fitness.tsb når du forklarer belastning.
- **Datakilde (ordbok):** computed_garmin_model

### `readiness.hrv_component`
**Readiness — HRV**

*enhet: `score` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** `5` (score)
- **Per dato:** `2026-05-31`
- **Definisjon:** HRV-komponent (0–100) basert på nylig RMSSD vs baseline.
- **Tolkning:** Lav score = autonom stress eller incomplete recovery.
- **Coaching:** Bruk sammen med recovery.hrv_delta_pct for narrativ.
- **Datakilde (ordbok):** computed_garmin_model

### `readiness.sleep_component`
**Readiness — søvn**

*enhet: `score` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** `5` (score)
- **Per dato:** `2026-05-31`
- **Definisjon:** Søvnkomponent (0–100) i Garmin readiness-modellen.
- **Tolkning:** Lav verdi tyder på utilstrekkelig eller dårlig søvn siste netter.
- **Coaching:** Forklar hvorfor rolig dag anbefales selv om athlete «føler seg ok».
- **Datakilde (ordbok):** computed_garmin_model

### `readiness.total_score`
**Garmin training readiness (total)**

*enhet: `score` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** `5` (score)
- **Per dato:** `2026-05-31`
- **Definisjon:** Samlet dags-score 0–100 fra TrainingReadinessService (søvn, HRV, form).
- **Tolkning:** Høyere er bedre. Under ~50: vurder lett økt. Under ~35: hvile.
- **Coaching:** Primær readiness for «kan jeg trene hardt i dag?»
- **Merk:** Ikke forveksle med readiness_score (coaching-heuristikk).
- **Datakilde (ordbok):** computed_garmin_model

## Kategori: `recovery`

### `activity.body_battery_delta`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «body_battery_delta». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `health.body_battery_max`

*enhet: `score` · scope: `stored` · kilde: `body_battery`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «body_battery_max». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `health.body_battery_min`

*enhet: `score` · scope: `stored` · kilde: `body_battery`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «body_battery_min». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `health.body_battery_net_charge`

*enhet: `score` · scope: `stored` · kilde: `body_battery`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «body_battery_net_charge». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `health.resting_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `resting_heart_rate`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «resting_heart_rate». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `recovery.hrv_baseline`

*enhet: `ms` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** HRV-baseline, recovery-score og predikert tid til baseline.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Forklar hvorfor hard trening bør utsettes eller tones ned.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `recovery.hrv_delta_pct`
**HRV avvik fra baseline (%)**

*enhet: `%` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Prosentvis avvik RMSSD vs 28-dagers baseline.
- **Tolkning:** Negativ = under normal — ofte tegn på stress/fatigue.
- **Coaching:** Forklar readiness og hvile anbefaling.
- **Datakilde (ordbok):** computed

### `recovery.predicted_hours_to_baseline`
**Predikert timer til baseline**

*enhet: `hours` · scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `26` (hours)
- **Per dato:** `2026-05-31`
- **Definisjon:** Heuristisk estimat (6–120 t) før readiness/TSB normaliseres.
- **Tolkning:** Høyere = mer hvile anbefales før hard økt.
- **Coaching:** Konkret «vent X timer» — merk at det er estimat, ikke Garmin.
- **Merk:** PPAP fase 3-heuristikk, ikke klinisk validert.
- **Datakilde (ordbok):** heuristic

### `recovery.recovery_efficiency_score`

*enhet: `score` · scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** HRV-baseline, recovery-score og predikert tid til baseline.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Forklar hvorfor hard trening bør utsettes eller tones ned.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

## Kategori: `risk`

### `injury_risk_score`
**Skaderisiko (heuristikk)**

*enhet: `score` · scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `2` (score)
- **Per dato:** `2026-05-31`
- **Definisjon:** Kombinasjon av ACWR, monotoni og overtraining.
- **Tolkning:** 0–100, høyere = mer risiko.
- **Coaching:** Advar — ikke medisinsk prognose.
- **Datakilde (ordbok):** heuristic

### `overtraining_score`
**Overtreningsscore**

*enhet: `score` · scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `33.3` (score)
- **Per dato:** `2026-05-31`
- **Definisjon:** Heuristikk fra belastning, form og HRV-flagg.
- **Tolkning:** Høyere = større risiko for overreaching.
- **Coaching:** Foreslå lett uke eller hvile.
- **Datakilde (ordbok):** heuristic

### `risk.overtraining_score`
**Overtreningsrisiko (alias)**

*enhet: `score` · scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `33.3` (score)
- **Per dato:** `2026-05-31`
- **Definisjon:** Samme konsept som overtraining_score.
- **Tolkning:** Se overtraining_score.
- **Datakilde (ordbok):** heuristic

## Kategori: `route`

### `route.hr_delta_pct`

*enhet: `%` · scope: `activity` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Sammenligning med tidligere økter på samme rute.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Objektiv progresjon uavhengig av vær og dagsform.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `route.performance_delta_pct`

*enhet: `%` · scope: `activity` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Sammenligning med tidligere økter på samme rute.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Objektiv progresjon uavhengig av vær og dagsform.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `route.power_delta_pct`

*enhet: `%` · scope: `activity` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Sammenligning med tidligere økter på samme rute.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Objektiv progresjon uavhengig av vær og dagsform.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `route_fingerprint.bbox_max_latitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.bbox_max_longitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.bbox_min_latitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.bbox_min_longitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.centroid_latitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.centroid_longitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.end_latitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.end_longitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.gps_point_count`

*enhet: `count` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.method_version`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.point_count`

*enhet: `count` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.quality_score`

*enhet: `score` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.route_distance_m`

*enhet: `m` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.sampled_point_count`

*enhet: `count` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.start_latitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_fingerprint.start_longitude`

*enhet: `value` · scope: `stored` · kilde: `activity_route_fingerprints`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.distance_ratio`

*enhet: `%` · scope: `stored` · kilde: `activity_route_matches`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.end_distance_m`

*enhet: `m` · scope: `stored` · kilde: `activity_route_matches`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.mean_distance_m`

*enhet: `m` · scope: `stored` · kilde: `activity_route_matches`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.method_version`

*enhet: `value` · scope: `stored` · kilde: `activity_route_matches`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.overlap_quality`

*enhet: `value` · scope: `stored` · kilde: `activity_route_matches`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.p90_distance_m`

*enhet: `m` · scope: `stored` · kilde: `activity_route_matches`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.reverse_direction`

*enhet: `value` · scope: `stored` · kilde: `activity_route_matches`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.same_route`

*enhet: `value` · scope: `stored` · kilde: `activity_route_matches`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.similarity_score`

*enhet: `score` · scope: `stored` · kilde: `activity_route_matches`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `route_match.start_distance_m`

*enhet: `m` · scope: `stored` · kilde: `activity_route_matches`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

## Kategori: `running`

### `running.critical_power`

*enhet: `W` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `running.critical_speed`
**Critical Speed**

*enhet: `m/s` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** CS fra hyperbolsk modell (m/s) på beste speed-efforts siste ~365 d.
- **Tolkning:** Høyere = bedre aerob/anaerob kapasitet.
- **Coaching:** Kapasitet og pacing for intervaller.
- **Datakilde (ordbok):** computed_fit

### `running.economy_hr`

*enhet: `ratio` · scope: `activity` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `running.economy_power`

*enhet: `ratio` · scope: `activity` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `running.form_degradation_index`

*enhet: `score` · scope: `activity` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `running.power_10m`
**Beste 10 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig effekt over 10 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_10m_hist`
**Beste 10 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste effekt over 10 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_1m`
**Beste 1 minutt effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig effekt over 1 minutt i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_1m_hist`
**Beste 1 minutt effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste effekt over 1 minutt fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_20m`
**Beste 20 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig effekt over 20 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_20m_hist`
**Beste 20 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste effekt over 20 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_30s`
**Beste 30 sekunder effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig effekt over 30 sekunder i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_30s_hist`
**Beste 30 sekunder effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste effekt over 30 sekunder fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_3m`
**Beste 3 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig effekt over 3 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_3m_hist`
**Beste 3 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste effekt over 3 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_40m`
**Beste 40 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig effekt over 40 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_40m_hist`
**Beste 40 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste effekt over 40 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_5m`
**Beste 5 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig effekt over 5 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_5m_hist`
**Beste 5 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste effekt over 5 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_60m`
**Beste 60 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig effekt over 60 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.power_60m_hist`
**Beste 60 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste effekt over 60 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_10m`
**Beste 10 minutter fart (snapshot)**

*enhet: `m/s` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig fart over 10 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_10m_hist`
**Beste 10 minutter fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste fart over 10 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_1m`
**Beste 1 minutt fart (snapshot)**

*enhet: `m/s` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig fart over 1 minutt i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_1m_hist`
**Beste 1 minutt fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste fart over 1 minutt fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_20m`
**Beste 20 minutter fart (snapshot)**

*enhet: `m/s` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig fart over 20 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_20m_hist`
**Beste 20 minutter fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste fart over 20 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_30s`
**Beste 30 sekunder fart (snapshot)**

*enhet: `m/s` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig fart over 30 sekunder i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_30s_hist`
**Beste 30 sekunder fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste fart over 30 sekunder fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_3m`
**Beste 3 minutter fart (snapshot)**

*enhet: `m/s` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig fart over 3 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_3m_hist`
**Beste 3 minutter fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste fart over 3 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_40m`
**Beste 40 minutter fart (snapshot)**

*enhet: `m/s` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig fart over 40 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_40m_hist`
**Beste 40 minutter fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste fart over 40 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_5m`
**Beste 5 minutter fart (snapshot)**

*enhet: `m/s` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig fart over 5 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_5m_hist`
**Beste 5 minutter fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste fart over 5 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_60m`
**Beste 60 minutter fart (snapshot)**

*enhet: `m/s` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Beste gjennomsnittlig fart over 60 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.speed_60m_hist`
**Beste 60 minutter fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Per dag: beste fart over 60 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde (ordbok):** computed_fit

### `running.w_prime`
**W′ (anaerob kapasitet)**

*enhet: `m` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Skjærepunkt D′ fra CS-modell (meter).
- **Tolkning:** Større W′ = mer «kick» over CS.
- **Coaching:** Forklar kort, hard innsats vs lang distanse.
- **Datakilde (ordbok):** computed_fit

### `running.w_prime_power`

*enhet: `W` · scope: `snapshot` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

## Kategori: `running_dynamics`

### `activity.average_running_cadence`

*enhet: `spm` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «average_running_cadence». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.stride_length`

*enhet: `m` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «stride_length». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.vertical_oscillation`

*enhet: `cm` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «vertical_oscillation». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.vertical_ratio`

*enhet: `%` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «vertical_ratio». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `sleep`

### `health.sleep_duration_s`

*enhet: `s` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «sleep_duration_s». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `health.sleep_overall_score`

*enhet: `score` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «sleep_overall_score». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `health.sleep_score`

*enhet: `score` · scope: `stored` · kilde: `sleep`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «sleep_score». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `sleep.consistency_score`

*enhet: `score` · scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Søvnlengde, kvalitet og akkumulert søvngjeld.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Koble dårlig søvn til anbefalt intensitet neste dag.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `sleep.sleep_debt_14d`

*enhet: `hours` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Søvnlengde, kvalitet og akkumulert søvngjeld.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Koble dårlig søvn til anbefalt intensitet neste dag.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `sleep.sleep_debt_28d`

*enhet: `hours` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Søvnlengde, kvalitet og akkumulert søvngjeld.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Koble dårlig søvn til anbefalt intensitet neste dag.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `sleep.sleep_debt_7d`
**Søvngjeld 7 dager**

*enhet: `hours` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Akkumulert timer under 8t søvn per natt.
- **Tolkning:** Høyere = mer uoppgjort søvn.
- **Coaching:** Forklar trøtthet uten hard trening.
- **Datakilde (ordbok):** computed

## Kategori: `stamina`

### `activity.begin_potential_stamina`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «begin_potential_stamina». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.end_potential_stamina`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «end_potential_stamina». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `stress`

### `health.high_stress_time_s`

*enhet: `s` · scope: `stored` · kilde: `stress`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «high_stress_time_s». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `health.stress_level`

*enhet: `score` · scope: `stored` · kilde: `stress`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Kolonne «stress_level». Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `summary`

### `daily_summary.avg_cadence`

*enhet: `value` · scope: `stored` · kilde: `daily_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.avg_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `daily_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.avg_pace`

*enhet: `s/km` · scope: `stored` · kilde: `daily_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.avg_speed`

*enhet: `m/s` · scope: `stored` · kilde: `daily_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.best_distance`

*enhet: `m` · scope: `stored` · kilde: `daily_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.best_duration`

*enhet: `%` · scope: `stored` · kilde: `daily_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.best_pace`

*enhet: `s/km` · scope: `stored` · kilde: `daily_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.best_speed`

*enhet: `m/s` · scope: `stored` · kilde: `daily_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.total_activities`

*enhet: `value` · scope: `stored` · kilde: `daily_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.total_ascent`

*enhet: `m` · scope: `stored` · kilde: `daily_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.total_calories`

*enhet: `kcal` · scope: `stored` · kilde: `daily_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.total_descent`

*enhet: `m` · scope: `stored` · kilde: `daily_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.total_distance`

*enhet: `m` · scope: `stored` · kilde: `daily_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `daily_summary.total_duration`

*enhet: `%` · scope: `stored` · kilde: `daily_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.activities_per_day`

*enhet: `value` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.activities_per_week`

*enhet: `value` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.activities_trend`

*enhet: `value` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.avg_cadence`

*enhet: `value` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.avg_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.avg_pace`

*enhet: `s/km` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.avg_speed`

*enhet: `m/s` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.best_distance`

*enhet: `m` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.best_duration`

*enhet: `%` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.best_pace`

*enhet: `s/km` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.best_speed`

*enhet: `m/s` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.distance_per_day`

*enhet: `m` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.distance_per_week`

*enhet: `m` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.distance_trend`

*enhet: `m` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.duration_per_day`

*enhet: `%` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.duration_per_week`

*enhet: `%` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.duration_trend`

*enhet: `%` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.month`

*enhet: `count` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.total_activities`

*enhet: `value` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.total_ascent`

*enhet: `m` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.total_calories`

*enhet: `kcal` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.total_descent`

*enhet: `m` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.total_distance`

*enhet: `m` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.total_duration`

*enhet: `%` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.total_tss`

*enhet: `value` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `monthly_summary.year`

*enhet: `count` · scope: `stored` · kilde: `monthly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.activities_per_day`

*enhet: `value` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.avg_cadence`

*enhet: `value` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.avg_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.avg_pace`

*enhet: `s/km` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.avg_speed`

*enhet: `m/s` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.best_distance`

*enhet: `m` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.best_duration`

*enhet: `%` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.best_pace`

*enhet: `s/km` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.best_speed`

*enhet: `m/s` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.distance_per_day`

*enhet: `m` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.duration_per_day`

*enhet: `%` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.total_activities`

*enhet: `value` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.total_ascent`

*enhet: `m` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.total_calories`

*enhet: `kcal` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.total_descent`

*enhet: `m` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.total_distance`

*enhet: `m` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.total_duration`

*enhet: `%` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.week_number`

*enhet: `count` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `weekly_summary.year`

*enhet: `count` · scope: `stored` · kilde: `weekly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.activities_per_day`

*enhet: `value` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.activities_per_month`

*enhet: `value` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.activities_per_week`

*enhet: `value` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.activities_trend`

*enhet: `value` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.avg_cadence`

*enhet: `value` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.avg_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.avg_pace`

*enhet: `s/km` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.avg_speed`

*enhet: `m/s` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.best_distance`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.best_duration`

*enhet: `%` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.best_pace`

*enhet: `s/km` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.best_speed`

*enhet: `m/s` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.distance_per_day`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.distance_per_month`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.distance_per_week`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.distance_trend`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.duration_per_day`

*enhet: `%` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.duration_per_month`

*enhet: `%` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.duration_per_week`

*enhet: `%` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.duration_trend`

*enhet: `%` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.total_activities`

*enhet: `value` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.total_ascent`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.total_calories`

*enhet: `kcal` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.total_descent`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.total_distance`

*enhet: `m` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `yearly_summary.total_duration`

*enhet: `%` · scope: `stored` · kilde: `yearly_summaries`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

## Kategori: `terrain`

### `activity.total_ascent`

*enhet: `m` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «total_ascent». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `threshold`

### `lactate_threshold.is_fallback`

*enhet: `value` · scope: `stored` · kilde: `lactate_threshold_history`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `lactate_threshold.lactate_threshold_heart_rate`

*enhet: `bpm` · scope: `stored` · kilde: `lactate_threshold_history`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `lactate_threshold.lactate_threshold_speed`

*enhet: `m/s` · scope: `stored` · kilde: `lactate_threshold_history`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `lactate_threshold.raw_lactate_threshold_speed`

*enhet: `m/s` · scope: `stored` · kilde: `lactate_threshold_history`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `lactate_threshold.source`

*enhet: `value` · scope: `stored` · kilde: `lactate_threshold_history`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

### `lactate_threshold.sync_context`

*enhet: `value` · scope: `stored` · kilde: `lactate_threshold_history`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.
- **Tolkning:** Ukjent — verifiser mot datakilde før sterke coaching-påstander.
- **Coaching:** Hent tidsserie og tolke forsiktig.
- **Datakilde (ordbok):** unknown

## Kategori: `training`

### `training.aerobic_score`

*enhet: `score` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Intensitetsfordeling og treningsklasser.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** 80/20, soner og om hard trening dominerer.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `training.anaerobic_score`

*enhet: `score` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Intensitetsfordeling og treningsklasser.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** 80/20, soner og om hard trening dominerer.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `training.class_1_pct`
**Treningsklasse 1 (Recovery) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Andel økttid klassifisert som Recovery siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.class_2_pct`
**Treningsklasse 2 (Lett) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Andel økttid klassifisert som Lett siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.class_3_pct`
**Treningsklasse 3 (Aerob) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Andel økttid klassifisert som Aerob siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.class_4_pct`
**Treningsklasse 4 (Tempo) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Andel økttid klassifisert som Tempo siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.class_5_pct`
**Treningsklasse 5 (Threshold) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Andel økttid klassifisert som Threshold siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.class_6_pct`
**Treningsklasse 6 (VO2) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Andel økttid klassifisert som VO2 siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.class_7_pct`
**Treningsklasse 7 (Anaerob) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Andel økttid klassifisert som Anaerob siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.class_8_pct`
**Treningsklasse 8 (Race) — andel tid**

*enhet: `%` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Andel økttid klassifisert som Race siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde (ordbok):** computed_lt

### `training.training_class`
**8-klassers sone (per økt)**

*enhet: `class` · scope: `activity` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** 1=recovery … 8=race, basert på puls vs LT1/LT2.
- **Tolkning:** Hele tall 1–8.
- **Coaching:** Detaljert intensitet på enkeltøkter.
- **Datakilde (ordbok):** computed_lt

### `training.training_zone`
**3-sones sone (per økt)**

*enhet: `zone` · scope: `activity` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** 1=under LT1, 2=mellom LT1–LT2, 3=over LT2 (snittpuls).
- **Tolkning:** Grov klassifisering per aktivitet.
- **Coaching:** Rask øktklassifisering — bruk class_* for finfordeling.
- **Datakilde (ordbok):** computed_lt

## Kategori: `training_effect`

### `activity.aerobic_training_effect`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «aerobic_training_effect». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.anaerobic_training_effect`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «anaerobic_training_effect». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `training_load`

### `activity.epoc`

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Kolonne «epoc». Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `activity.training_stress_score`
**Training Stress Score (TSS)**

*enhet: `score` · scope: `stored` · kilde: `activities`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Belastningsscore per økt (≈ EPOC fra Garmin der tilgjengelig).
- **Tolkning:** 100 ≈ 1 time ved terskel; summeres til CTL/ATL.
- **Coaching:** Volum og intensitet per uke.
- **Datakilde (ordbok):** garmin_or_estimated

### `load.acwr`
**Acute:Chronic Workload Ratio**

*enhet: `ratio` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Akutt/kronisk belastningsforhold (Garmin eller coaching-fallback).
- **Tolkning:** ~0.8–1.3 ofte trygt; >1.5 øker skaderisiko i litteraturen.
- **Coaching:** Advar ved brå økning i belastning.
- **Datakilde (ordbok):** garmin_or_computed

### `load.monotony`
**Treningsmonotoni**

*enhet: `ratio` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Snitt belastning / standardavvik siste 7 dager.
- **Tolkning:** Høy monotoni = lite variasjon dag til dag.
- **Coaching:** Anbefal variasjon eller hviledag ved høy monotoni + høy strain.
- **Datakilde (ordbok):** computed

### `load.strain`
**Treningsstrain**

*enhet: `score` · scope: `daily` · kilde: `derived`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Ukes sum TSS multiplisert med monotoni.
- **Tolkning:** Høy strain = mye volum med lite variasjon.
- **Coaching:** Kombiner med monotony for overtreningssignal.
- **Datakilde (ordbok):** computed

### `performance.acwr_percent`

*enhet: `%` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «acwr_percent». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.daily_training_load_acute`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «daily_training_load_acute». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

### `performance.daily_training_load_chronic`

*enhet: `score` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «daily_training_load_chronic». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `training_status`

### `performance.training_status`

*enhet: `code` · scope: `stored` · kilde: `garmin_performance_metrics`*

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Kolonne «training_status». Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Merk:** Auto-oppdaget lagret felt — ingen manuell definisjon ennå.
- **Datakilde (ordbok):** garmin_sync

## Kategori: `weather`

### `weather.adjusted_pace`

*enhet: `s/km` · scope: `activity` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Temperaturjustert pace og estimert prestasjonstap.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Normaliser langsomme økter i varme/kulde.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

### `weather.performance_penalty_pct`

*enhet: `%` · scope: `activity` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Temperaturjustert pace og estimert prestasjonstap.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Normaliser langsomme økter i varme/kulde.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde (ordbok):** derived

---

## Ordbok uten katalogoppføring

12 nøkler i ordbok som ikke er i `metric_catalog`. 4 har beregnet verdi i dag.

### `activity.decoupling_percent`
**Aerobic decoupling**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Prosent fall i efficiency factor fra 1. til 2. halvdel av økten.
- **Tolkning:** Positiv = mer puls per fart sent i økta (aerob stress).
- **Coaching:** Kun på steady-state økter >45 min; se suitability-flagg.
- **Datakilde (ordbok):** computed_fit

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

- **Nåværende verdi:** *(ingen verdi)*
- **Definisjon:** Hvor nær 80/20-fordeling (lav/høy) brukeren er.
- **Tolkning:** 100 = ideell polarisert profil siste 28 dager.
- **Coaching:** Juster volum mot rolig vs hard trening.
- **Datakilde (ordbok):** computed

### `coaching.recommended_workout`
**Anbefalt neste økt**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `easy_run`
- **Per dato:** `2026-05-31`
- **Definisjon:** Enum: rest, recovery_run, easy_run, threshold, vo2_intervals, long_run, …
- **Tolkning:** Samlet anbefaling fra readiness, belastning og treningsfase.
- **Coaching:** Konkret «hva bør du gjøre i dag».
- **Datakilde (ordbok):** heuristic

### `consistency.score`
**Training Consistency Score**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** ``
- **Per dato:** `2026-05-31`
- **Definisjon:** Andel av siste 28 dager med minst én løpeøkt (0–100).
- **Tolkning:** 85+ svært bra, 70–85 bra, under 60 inkonsistent.
- **Coaching:** Vurder om fremgang stoppes av hull i treningen, ikke bare CTL.
- **Datakilde (ordbok):** computed

### `fitness.gain_rate`
**Fitness gain rate (CTL)**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** ``
- **Per dato:** `2026-05-31`
- **Definisjon:** Endring i CTL per dag over siste 42 dager.
- **Tolkning:** Positiv = bygger form; negativ = taper eller sykdom.
- **Coaching:** Retning viktigere enn dagens CTL-nivå.
- **Datakilde (ordbok):** computed

### `readiness.5k`
**Event readiness 5K**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** `58`
- **Per dato:** `2026-05-31`
- **Definisjon:** Konkurransespesifikk readiness 0–100 for 5 km.
- **Tolkning:** Kombinerer Garmin readiness, TSB, HRV og søvn for kort race.
- **Coaching:** Anbefal start eller utsettelse av 5K/10K.
- **Datakilde (ordbok):** heuristic

### `running.durability_score`
**Durability score**

*scope: `daily` · kilde: `derived` · **heuristikk***

- **Nåværende verdi:** *(ingen verdi)*
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

- Med verdi: **17** / 404
- Uten verdi: **387**
