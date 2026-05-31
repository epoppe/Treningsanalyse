# Metric glossary (MCP / PPAP)

Ordbok for alle metrikker som kan spørres via MCP (`metric_catalog`, 
`query_metric_timeseries`, `metric_glossary`). Bruk denne når du coacher 
eller skriver prompts — **ikke** bland metrikker som ser like ut.

> Generert fra `backend/app/mcp/metric_glossary.py`. Kjør på nytt: 
`cd backend && python3 scripts/generate_metric_glossary_md.py`

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

## Scope (tidsoppløsning)

| Scope | Betydning |
|-------|-----------|
| `activity` | Én verdi per treningsøkt. |
| `daily` | Beregnet én verdi per kalenderdag. |
| `rolling_daily` | Daglig verdi basert på rullerende vindu (f.eks. 365 dager tilbake). |
| `snapshot` | Én gjeldende verdi (typisk siste beregning / all-time). |
| `stored` | Verdi lagret i database per aktivitet eller døgn (Garmin/sync). |

---

## Kategorier (oversikt)

### `activity`
- **Definisjon:** Rå eller Garmin-beregnet verdi knyttet til én treningsøkt.
- **Coaching:** Bruk for konkret øktanalyse, ikke for langsiktig trend uten aggregat.

### `cardio`
- **Definisjon:** HRV, puls og aerob drift over tid.
- **Coaching:** Recovery-trend og tegn på stress/utmattelse.

### `coaching`
- **Definisjon:** Interne heuristiske scorer og drivere — ikke offisielle Garmin-score.
- **Coaching:** Suppler Garmin-data; merk alltid at det er modellert.

### `fitness`
- **Definisjon:** CTL/ATL/TSB og aerob effektivitet (EF) fra lokal TSS-modell.
- **Coaching:** Form, fitness og om athlete er fresh eller sliten.

### `performance`
- **Definisjon:** VO2, predikerte løpstider og Garmin performance-felter.
- **Coaching:** Kapasitet og målsetting — prediksjoner er modellbaserte.

### `readiness`
- **Definisjon:** Dagsform basert på søvn, HRV og treningsbalanse (Garmin-modell).
- **Coaching:** Anbefal hard / moderat / lett / hvile for dagens økt.

### `recovery`
- **Definisjon:** HRV-baseline, recovery-score og predikert tid til baseline.
- **Coaching:** Forklar hvorfor hard trening bør utsettes eller tones ned.

### `risk`
- **Definisjon:** Heuristiske risikoscore for overtrening og skade.
- **Coaching:** Advar ved høye verdier; ikke bruk som medisinsk diagnose.

### `route`
- **Definisjon:** Sammenligning med tidligere økter på samme rute.
- **Coaching:** Objektiv progresjon uavhengig av vær og dagsform.

### `running`
- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.

### `sleep`
- **Definisjon:** Søvnlengde, kvalitet og akkumulert søvngjeld.
- **Coaching:** Koble dårlig søvn til anbefalt intensitet neste dag.

### `training`
- **Definisjon:** Intensitetsfordeling og treningsklasser.
- **Coaching:** 80/20, soner og om hard trening dominerer.

### `training_load`
- **Definisjon:** Akutt/kronisk belastning og risiko for monotoni.
- **Coaching:** Vurder om volum og intensitet er bærekraftig denne uken.

### `weather`
- **Definisjon:** Temperaturjustert pace og estimert prestasjonstap.
- **Coaching:** Normaliser langsomme økter i varme/kulde.

---

## Beregnete metrikker (derived)

## Kategori: `cardio`

### `cardio.drift_score`
**Cardio drift score**

*enhet: `score` · scope: `daily` · heuristikk: ja*

- **Definisjon:** 100 minus typisk HR-drift/decoupling — høyere er bedre.
- **Tolkning:** Lav score = dårlig aerob stabilitet i perioden.
- **Coaching:** Aerob kvalitet over flere økter.
- **Datakilde:** heuristic

### `cardio.hrv_30d`

*enhet: `ms` · scope: `daily`*

- **Definisjon:** HRV, puls og aerob drift over tid.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Recovery-trend og tegn på stress/utmattelse.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `cardio.hrv_7d`
**HRV 7-dagers snitt**

*enhet: `ms` · scope: `daily`*

- **Definisjon:** Snitt RMSSD siste 7 dager.
- **Tolkning:** Sammenlign med baseline og recovery.hrv_baseline.
- **Coaching:** Kort trend — ikke overtolking av én dag.
- **Datakilde:** stored_hrv

### `cardio.hrv_90d`

*enhet: `ms` · scope: `daily`*

- **Definisjon:** HRV, puls og aerob drift over tid.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Recovery-trend og tegn på stress/utmattelse.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `cardio.rhr_30d`

*enhet: `bpm` · scope: `daily`*

- **Definisjon:** HRV, puls og aerob drift over tid.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Recovery-trend og tegn på stress/utmattelse.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `cardio.rhr_7d`

*enhet: `bpm` · scope: `daily`*

- **Definisjon:** HRV, puls og aerob drift over tid.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Recovery-trend og tegn på stress/utmattelse.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

## Kategori: `coaching`

### `coaching.zone1_pct`
**Lav intensitet (soner 1)**

*enhet: `%` · scope: `daily`*

- **Definisjon:** Andel økttid under LT1 (Seiler lav sone).
- **Tolkning:** Mål ~75–85 % for polarisert 80/20.
- **Coaching:** Flagg for lite rolig volum.
- **Datakilde:** computed_lt

### `coaching.zone2_pct`
**Threshold-sone (soner 2)**

*enhet: `%` · scope: `daily`*

- **Definisjon:** Andel tid mellom LT1 og LT2.
- **Tolkning:** Bør typisk være lav (<15 %) i polarisert modell.
- **Coaching:** Advar ved «grå sone»-dominans.
- **Datakilde:** computed_lt

### `coaching.zone3_pct`
**Høy intensitet (soner 3)**

*enhet: `%` · scope: `daily`*

- **Definisjon:** Andel tid over LT2.
- **Tolkning:** Noen få prosent er ofte nok; for mye øker fatigue.
- **Coaching:** Balanser med zone1_pct.
- **Datakilde:** computed_lt

### `fatigue_score`
**Fatigue score (coaching)**

*enhet: `score` · scope: `daily` · heuristikk: ja*

- **Definisjon:** Normalisert fatigue fra Banister (0–100).
- **Tolkning:** Høyere = mer akutt tretthet.
- **Coaching:** Par med fitness_score.
- **Datakilde:** heuristic

### `fitness_score`
**Fitness score (coaching)**

*enhet: `score` · scope: `daily` · heuristikk: ja*

- **Definisjon:** Normalisert Banister-fitness (0–100).
- **Tolkning:** Høyere = høyere kronisk fitness i modellen.
- **Coaching:** Forenklet fitness for narrativ.
- **Datakilde:** heuristic

### `performance_driver_name`
**Sterkest negativ driver**

*enhet: `label` · scope: `snapshot` · heuristikk: ja*

- **Definisjon:** Faktornavn med høyest vektet avvik (HRV, søvn, belastning, …).
- **Tolkning:** Tekstlabel, ikke numerisk score.
- **Coaching:** Start coaching-svar med «hovedårsak akkurat nå er …»
- **Datakilde:** heuristic_ml

### `performance_driver_weight`
**Driver-vekt**

*enhet: `ratio` · scope: `snapshot` · heuristikk: ja*

- **Definisjon:** Normalisert andel (0–1) av hvor mye den valgte driveren dominerer.
- **Tolkning:** Høyere = mer relevant å adressere først.
- **Coaching:** Prioriter tiltak etter vekt.
- **Datakilde:** heuristic_ml

### `performance_score`
**Performance score (coaching)**

*enhet: `score` · scope: `daily` · heuristikk: ja*

- **Definisjon:** Banister performance (fitness − fatigue) skalert 0–100.
- **Tolkning:** Høyere = bedre dagsform i modellen.
- **Coaching:** Dags «form» i coaching-språk.
- **Datakilde:** heuristic

### `readiness_score`
**Coaching readiness (heuristikk)**

*enhet: `score` · scope: `daily` · heuristikk: ja*

- **Definisjon:** Intern score fra recovery + Banister-form — ikke Garmin.
- **Tolkning:** 0–100, høyere = bedre dagsform i coaching-modellen.
- **Coaching:** Kun når du eksplisitt bruker coaching-modellen, ikke Garmin UI.
- **Merk:** Erstatter ikke readiness.total_score.
- **Datakilde:** heuristic

### `recovery_score`
**Recovery score (coaching)**

*enhet: `score` · scope: `daily` · heuristikk: ja*

- **Definisjon:** Sammensatt recovery fra HRV, søvn og puls.
- **Tolkning:** Høyere = bedre recovery-status.
- **Coaching:** Ikke Garmin readiness — intern.
- **Datakilde:** heuristic

## Kategori: `fitness`

### `fitness.atl`
**Acute Training Load (ATL)**

*enhet: `load` · scope: `daily`*

- **Definisjon:** 7-dagers eksponentiell glidende snitt av daglig TSS/EPOC.
- **Tolkning:** Reagerer raskt på nylige harde økter.
- **Coaching:** Forklar «hvor sliten er du nå» vs CTL (fitness).
- **Datakilde:** computed_tss

### `fitness.ctl`
**Chronic Training Load (CTL)**

*enhet: `load` · scope: `daily`*

- **Definisjon:** 42-dagers eksponentiell glidende snitt av daglig TSS/EPOC.
- **Tolkning:** Høyere = mer kronisk treningsvolum (fitness). Stiger sakte.
- **Coaching:** Beskriv langsiktig treningsstatus og kapasitet.
- **Datakilde:** computed_tss

### `fitness.ef_30d`
**Aerob effektivitet (30 dager)**

*enhet: `m_per_s_per_bpm` · scope: `daily`*

- **Definisjon:** Rullerende snitt av speed/HR (m/s per bpm) på rolige økter.
- **Tolkning:** Høyere = bedre økonomi ved lav intensitet over tid.
- **Coaching:** Trend for aerob utvikling — sammenlign over uker, ikke én økt.
- **Datakilde:** computed

### `fitness.ef_60d`

*enhet: `m_per_s_per_bpm` · scope: `daily`*

- **Definisjon:** CTL/ATL/TSB og aerob effektivitet (EF) fra lokal TSS-modell.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Form, fitness og om athlete er fresh eller sliten.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `fitness.ef_90d`

*enhet: `m_per_s_per_bpm` · scope: `daily`*

- **Definisjon:** CTL/ATL/TSB og aerob effektivitet (EF) fra lokal TSS-modell.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Form, fitness og om athlete er fresh eller sliten.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `fitness.form`
**Form (alias TSB)**

*enhet: `load` · scope: `daily`*

- **Definisjon:** Samme som fitness.tsb.
- **Tolkning:** Se fitness.tsb.
- **Coaching:** Se fitness.tsb.
- **Datakilde:** computed_tss

### `fitness.tsb`
**Training Stress Balance (TSB / Form)**

*enhet: `load` · scope: `daily`*

- **Definisjon:** CTL minus ATL. Positiv = relativt fresh, negativ = akkumulert fatigue.
- **Tolkning:** Omtrent −10 til +10 er ofte normalt i opplæring; svært negativ = risiko.
- **Coaching:** Kjerne for taper, overreaching og restitusjonsdager.
- **Datakilde:** computed_tss

## Kategori: `performance`

### `predicted_10k_time`

*enhet: `s` · scope: `snapshot` · heuristikk: ja*

- **Definisjon:** VO2, predikerte løpstider og Garmin performance-felter.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet og målsetting — prediksjoner er modellbaserte.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `predicted_5k_time`
**Predikert 5 km-tid**

*enhet: `s` · scope: `snapshot` · heuristikk: ja*

- **Definisjon:** Estimert tid fra CS + W′-modell.
- **Tolkning:** Sekunder — lavere er raskere.
- **Coaching:** Målsetting — kun ved god CS-modellkvalitet.
- **Datakilde:** heuristic

### `predicted_half_marathon_time`

*enhet: `s` · scope: `snapshot` · heuristikk: ja*

- **Definisjon:** VO2, predikerte løpstider og Garmin performance-felter.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet og målsetting — prediksjoner er modellbaserte.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `predicted_marathon_time`

*enhet: `s` · scope: `snapshot` · heuristikk: ja*

- **Definisjon:** VO2, predikerte løpstider og Garmin performance-felter.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet og målsetting — prediksjoner er modellbaserte.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

## Kategori: `readiness`

### `readiness.form_component`
**Readiness — form (TSB)**

*enhet: `score` · scope: `daily`*

- **Definisjon:** Form/TSB normalisert til 0–100 (tung vekt i total score).
- **Tolkning:** Reflekterer CTL−ATL; lav score = høy akutt tretthet.
- **Coaching:** Koble til fitness.tsb når du forklarer belastning.
- **Datakilde:** computed_garmin_model

### `readiness.hrv_component`
**Readiness — HRV**

*enhet: `score` · scope: `daily`*

- **Definisjon:** HRV-komponent (0–100) basert på nylig RMSSD vs baseline.
- **Tolkning:** Lav score = autonom stress eller incomplete recovery.
- **Coaching:** Bruk sammen med recovery.hrv_delta_pct for narrativ.
- **Datakilde:** computed_garmin_model

### `readiness.sleep_component`
**Readiness — søvn**

*enhet: `score` · scope: `daily`*

- **Definisjon:** Søvnkomponent (0–100) i Garmin readiness-modellen.
- **Tolkning:** Lav verdi tyder på utilstrekkelig eller dårlig søvn siste netter.
- **Coaching:** Forklar hvorfor rolig dag anbefales selv om athlete «føler seg ok».
- **Datakilde:** computed_garmin_model

### `readiness.total_score`
**Garmin training readiness (total)**

*enhet: `score` · scope: `daily`*

- **Definisjon:** Samlet dags-score 0–100 fra TrainingReadinessService (søvn, HRV, form).
- **Tolkning:** Høyere er bedre. Under ~50: vurder lett økt. Under ~35: hvile.
- **Coaching:** Primær readiness for «kan jeg trene hardt i dag?»
- **Merk:** Ikke forveksle med readiness_score (coaching-heuristikk).
- **Datakilde:** computed_garmin_model

## Kategori: `recovery`

### `recovery.hrv_baseline`

*enhet: `ms` · scope: `daily`*

- **Definisjon:** HRV-baseline, recovery-score og predikert tid til baseline.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Forklar hvorfor hard trening bør utsettes eller tones ned.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `recovery.hrv_delta_pct`
**HRV avvik fra baseline (%)**

*enhet: `%` · scope: `daily`*

- **Definisjon:** Prosentvis avvik RMSSD vs 28-dagers baseline.
- **Tolkning:** Negativ = under normal — ofte tegn på stress/fatigue.
- **Coaching:** Forklar readiness og hvile anbefaling.
- **Datakilde:** computed

### `recovery.predicted_hours_to_baseline`
**Predikert timer til baseline**

*enhet: `hours` · scope: `daily` · heuristikk: ja*

- **Definisjon:** Heuristisk estimat (6–120 t) før readiness/TSB normaliseres.
- **Tolkning:** Høyere = mer hvile anbefales før hard økt.
- **Coaching:** Konkret «vent X timer» — merk at det er estimat, ikke Garmin.
- **Merk:** PPAP fase 3-heuristikk, ikke klinisk validert.
- **Datakilde:** heuristic

### `recovery.recovery_efficiency_score`

*enhet: `score` · scope: `daily` · heuristikk: ja*

- **Definisjon:** HRV-baseline, recovery-score og predikert tid til baseline.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Forklar hvorfor hard trening bør utsettes eller tones ned.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

## Kategori: `risk`

### `injury_risk_score`
**Skaderisiko (heuristikk)**

*enhet: `score` · scope: `daily` · heuristikk: ja*

- **Definisjon:** Kombinasjon av ACWR, monotoni og overtraining.
- **Tolkning:** 0–100, høyere = mer risiko.
- **Coaching:** Advar — ikke medisinsk prognose.
- **Datakilde:** heuristic

### `overtraining_score`
**Overtreningsscore**

*enhet: `score` · scope: `daily` · heuristikk: ja*

- **Definisjon:** Heuristikk fra belastning, form og HRV-flagg.
- **Tolkning:** Høyere = større risiko for overreaching.
- **Coaching:** Foreslå lett uke eller hvile.
- **Datakilde:** heuristic

### `risk.overtraining_score`
**Overtreningsrisiko (alias)**

*enhet: `score` · scope: `daily` · heuristikk: ja*

- **Definisjon:** Samme konsept som overtraining_score.
- **Tolkning:** Se overtraining_score.
- **Datakilde:** heuristic

## Kategori: `route`

### `route.hr_delta_pct`

*enhet: `%` · scope: `activity`*

- **Definisjon:** Sammenligning med tidligere økter på samme rute.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Objektiv progresjon uavhengig av vær og dagsform.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `route.performance_delta_pct`

*enhet: `%` · scope: `activity`*

- **Definisjon:** Sammenligning med tidligere økter på samme rute.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Objektiv progresjon uavhengig av vær og dagsform.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `route.power_delta_pct`

*enhet: `%` · scope: `activity`*

- **Definisjon:** Sammenligning med tidligere økter på samme rute.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Objektiv progresjon uavhengig av vær og dagsform.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

## Kategori: `running`

### `running.critical_power`

*enhet: `W` · scope: `snapshot`*

- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `running.critical_speed`
**Critical Speed**

*enhet: `m/s` · scope: `snapshot`*

- **Definisjon:** CS fra hyperbolsk modell (m/s) på beste speed-efforts siste ~365 d.
- **Tolkning:** Høyere = bedre aerob/anaerob kapasitet.
- **Coaching:** Kapasitet og pacing for intervaller.
- **Datakilde:** computed_fit

### `running.economy_hr`

*enhet: `ratio` · scope: `activity`*

- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `running.economy_power`

*enhet: `ratio` · scope: `activity`*

- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `running.form_degradation_index`

*enhet: `score` · scope: `activity`*

- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `running.power_10m`
**Beste 10 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig effekt over 10 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.power_10m_hist`
**Beste 10 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste effekt over 10 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.power_1m`
**Beste 1 minutt effekt (snapshot)**

*enhet: `W` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig effekt over 1 minutt i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.power_1m_hist`
**Beste 1 minutt effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste effekt over 1 minutt fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.power_20m`
**Beste 20 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig effekt over 20 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.power_20m_hist`
**Beste 20 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste effekt over 20 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.power_30s`
**Beste 30 sekunder effekt (snapshot)**

*enhet: `W` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig effekt over 30 sekunder i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.power_30s_hist`
**Beste 30 sekunder effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste effekt over 30 sekunder fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.power_3m`
**Beste 3 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig effekt over 3 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.power_3m_hist`
**Beste 3 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste effekt over 3 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.power_40m`
**Beste 40 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig effekt over 40 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.power_40m_hist`
**Beste 40 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste effekt over 40 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.power_5m`
**Beste 5 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig effekt over 5 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.power_5m_hist`
**Beste 5 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste effekt over 5 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.power_60m`
**Beste 60 minutter effekt (snapshot)**

*enhet: `W` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig effekt over 60 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere W = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.power_60m_hist`
**Beste 60 minutter effekt (365d rullerende)**

*enhet: `W` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste effekt over 60 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.speed_10m`
**Beste 10 minutter fart (snapshot)**

*enhet: `m/s` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig fart over 10 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.speed_10m_hist`
**Beste 10 minutter fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste fart over 10 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.speed_1m`
**Beste 1 minutt fart (snapshot)**

*enhet: `m/s` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig fart over 1 minutt i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.speed_1m_hist`
**Beste 1 minutt fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste fart over 1 minutt fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.speed_20m`
**Beste 20 minutter fart (snapshot)**

*enhet: `m/s` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig fart over 20 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.speed_20m_hist`
**Beste 20 minutter fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste fart over 20 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.speed_30s`
**Beste 30 sekunder fart (snapshot)**

*enhet: `m/s` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig fart over 30 sekunder i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.speed_30s_hist`
**Beste 30 sekunder fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste fart over 30 sekunder fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.speed_3m`
**Beste 3 minutter fart (snapshot)**

*enhet: `m/s` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig fart over 3 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.speed_3m_hist`
**Beste 3 minutter fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste fart over 3 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.speed_40m`
**Beste 40 minutter fart (snapshot)**

*enhet: `m/s` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig fart over 40 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.speed_40m_hist`
**Beste 40 minutter fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste fart over 40 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.speed_5m`
**Beste 5 minutter fart (snapshot)**

*enhet: `m/s` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig fart over 5 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.speed_5m_hist`
**Beste 5 minutter fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste fart over 5 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.speed_60m`
**Beste 60 minutter fart (snapshot)**

*enhet: `m/s` · scope: `snapshot`*

- **Definisjon:** Beste gjennomsnittlig fart over 60 minutter i snapshot (ofte all-time).
- **Tolkning:** Høyere m/s = bedre for den varigheten.
- **Coaching:** Kapasitetspunkt på duration curve.
- **Datakilde:** computed_fit

### `running.speed_60m_hist`
**Beste 60 minutter fart (365d rullerende)**

*enhet: `m/s` · scope: `rolling_daily`*

- **Definisjon:** Per dag: beste fart over 60 minutter fra siste 365 dager.
- **Tolkning:** Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.
- **Coaching:** Historisk utvikling på duration curve.
- **Datakilde:** computed_fit

### `running.w_prime`
**W′ (anaerob kapasitet)**

*enhet: `m` · scope: `snapshot`*

- **Definisjon:** Skjærepunkt D′ fra CS-modell (meter).
- **Tolkning:** Større W′ = mer «kick» over CS.
- **Coaching:** Forklar kort, hard innsats vs lang distanse.
- **Datakilde:** computed_fit

### `running.w_prime_power`

*enhet: `W` · scope: `snapshot`*

- **Definisjon:** Løpsprestasjon, kurver og økonomi fra FIT/effort-data.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Kapasitet, fart over varighet, og aerob effektivitet.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

## Kategori: `sleep`

### `sleep.consistency_score`

*enhet: `score` · scope: `daily` · heuristikk: ja*

- **Definisjon:** Søvnlengde, kvalitet og akkumulert søvngjeld.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Koble dårlig søvn til anbefalt intensitet neste dag.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `sleep.sleep_debt_14d`

*enhet: `hours` · scope: `daily`*

- **Definisjon:** Søvnlengde, kvalitet og akkumulert søvngjeld.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Koble dårlig søvn til anbefalt intensitet neste dag.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `sleep.sleep_debt_28d`

*enhet: `hours` · scope: `daily`*

- **Definisjon:** Søvnlengde, kvalitet og akkumulert søvngjeld.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Koble dårlig søvn til anbefalt intensitet neste dag.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `sleep.sleep_debt_7d`
**Søvngjeld 7 dager**

*enhet: `hours` · scope: `daily`*

- **Definisjon:** Akkumulert timer under 8t søvn per natt.
- **Tolkning:** Høyere = mer uoppgjort søvn.
- **Coaching:** Forklar trøtthet uten hard trening.
- **Datakilde:** computed

## Kategori: `training`

### `training.aerobic_score`

*enhet: `score` · scope: `daily`*

- **Definisjon:** Intensitetsfordeling og treningsklasser.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** 80/20, soner og om hard trening dominerer.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `training.anaerobic_score`

*enhet: `score` · scope: `daily`*

- **Definisjon:** Intensitetsfordeling og treningsklasser.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** 80/20, soner og om hard trening dominerer.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `training.class_1_pct`
**Treningsklasse 1 (Recovery) — andel tid**

*enhet: `%` · scope: `daily`*

- **Definisjon:** Andel økttid klassifisert som Recovery siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde:** computed_lt

### `training.class_2_pct`
**Treningsklasse 2 (Lett) — andel tid**

*enhet: `%` · scope: `daily`*

- **Definisjon:** Andel økttid klassifisert som Lett siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde:** computed_lt

### `training.class_3_pct`
**Treningsklasse 3 (Aerob) — andel tid**

*enhet: `%` · scope: `daily`*

- **Definisjon:** Andel økttid klassifisert som Aerob siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde:** computed_lt

### `training.class_4_pct`
**Treningsklasse 4 (Tempo) — andel tid**

*enhet: `%` · scope: `daily`*

- **Definisjon:** Andel økttid klassifisert som Tempo siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde:** computed_lt

### `training.class_5_pct`
**Treningsklasse 5 (Threshold) — andel tid**

*enhet: `%` · scope: `daily`*

- **Definisjon:** Andel økttid klassifisert som Threshold siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde:** computed_lt

### `training.class_6_pct`
**Treningsklasse 6 (VO2) — andel tid**

*enhet: `%` · scope: `daily`*

- **Definisjon:** Andel økttid klassifisert som VO2 siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde:** computed_lt

### `training.class_7_pct`
**Treningsklasse 7 (Anaerob) — andel tid**

*enhet: `%` · scope: `daily`*

- **Definisjon:** Andel økttid klassifisert som Anaerob siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde:** computed_lt

### `training.class_8_pct`
**Treningsklasse 8 (Race) — andel tid**

*enhet: `%` · scope: `daily`*

- **Definisjon:** Andel økttid klassifisert som Race siste 28 dager.
- **Tolkning:** Prosent av total løpetid; summer til ~100 %.
- **Coaching:** Finfordeling utover 3-soners coaching.zone*.
- **Datakilde:** computed_lt

### `training.training_class`
**8-klassers sone (per økt)**

*enhet: `class` · scope: `activity`*

- **Definisjon:** 1=recovery … 8=race, basert på puls vs LT1/LT2.
- **Tolkning:** Hele tall 1–8.
- **Coaching:** Detaljert intensitet på enkeltøkter.
- **Datakilde:** computed_lt

### `training.training_zone`
**3-sones sone (per økt)**

*enhet: `zone` · scope: `activity`*

- **Definisjon:** 1=under LT1, 2=mellom LT1–LT2, 3=over LT2 (snittpuls).
- **Tolkning:** Grov klassifisering per aktivitet.
- **Coaching:** Rask øktklassifisering — bruk class_* for finfordeling.
- **Datakilde:** computed_lt

## Kategori: `training_load`

### `load.acwr`
**Acute:Chronic Workload Ratio**

*enhet: `ratio` · scope: `daily`*

- **Definisjon:** Akutt/kronisk belastningsforhold (Garmin eller coaching-fallback).
- **Tolkning:** ~0.8–1.3 ofte trygt; >1.5 øker skaderisiko i litteraturen.
- **Coaching:** Advar ved brå økning i belastning.
- **Datakilde:** garmin_or_computed

### `load.monotony`
**Treningsmonotoni**

*enhet: `ratio` · scope: `daily`*

- **Definisjon:** Snitt belastning / standardavvik siste 7 dager.
- **Tolkning:** Høy monotoni = lite variasjon dag til dag.
- **Coaching:** Anbefal variasjon eller hviledag ved høy monotoni + høy strain.
- **Datakilde:** computed

### `load.strain`
**Treningsstrain**

*enhet: `score` · scope: `daily`*

- **Definisjon:** Ukes sum TSS multiplisert med monotoni.
- **Tolkning:** Høy strain = mye volum med lite variasjon.
- **Coaching:** Kombiner med monotony for overtreningssignal.
- **Datakilde:** computed

## Kategori: `weather`

### `weather.adjusted_pace`

*enhet: `s/km` · scope: `activity` · heuristikk: ja*

- **Definisjon:** Temperaturjustert pace og estimert prestasjonstap.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Normaliser langsomme økter i varme/kulde.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

### `weather.performance_penalty_pct`

*enhet: `%` · scope: `activity` · heuristikk: ja*

- **Definisjon:** Temperaturjustert pace og estimert prestasjonstap.
- **Tolkning:** Se category_glossary og metric_catalog.
- **Coaching:** Normaliser langsomme økter i varme/kulde.
- **Merk:** Mangler detaljert oppføring.
- **Datakilde:** derived

---

## Lagrede metrikker (Garmin/sync)

Disse hentes fra databasekolonner. De fleste har generisk forklaring via prefiks nedenfor; viktige felt har egne oppføringer i koden.

### Prefiks-mønstre

#### `activity.*`
- **Definisjon:** Verdi fra én synkronisert Garmin/FIT-aktivitet.
- **Tolkning:** Se aktivitetskontekst (varighet, type, terreng).
- **Coaching:** Øktanalyse og sammenligning med lignende økter.
- **Kilde:** garmin_sync

#### `health.*`
- **Definisjon:** Daglig helsemetric (søvn, HRV, puls, body battery).
- **Tolkning:** Trend viktigere enn enkeltdag.
- **Coaching:** Recovery og livsstilsfaktorer.
- **Kilde:** garmin_sync

#### `performance.*`
- **Definisjon:** Garmin performance status (VO2, load balance, scores).
- **Tolkning:** Offisiell Garmin-modell der merket.
- **Coaching:** Kapasitet og treningsstatus fra Garmin.
- **Kilde:** garmin_sync

### Full liste lagrede nøkler (alfabetisk per kategori)

#### `acclimation` (2 nøkler)

- `performance.altitude_acclimation` — Garmin performance status (VO2, load balance, scores). *(enhet: m, scope: stored)*
- `performance.heat_acclimation` — Garmin performance status (VO2, load balance, scores). *(enhet: %, scope: stored)*

#### `activity` (54 nøkler)

- `activity.activity_body_battery_delta` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.aerobic_training_effect_message` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*
- `activity.anaerobic_training_effect_message` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*
- `activity.average_heart_rate` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: bpm, scope: stored)*
- `activity.average_moving_speed` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m/s, scope: stored)*
- `activity.average_pace` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: s/km, scope: stored)*
- `activity.average_speed` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m/s, scope: stored)*
- `activity.average_speed_mps` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m/s, scope: stored)*
- `activity.avg_efficiency_factor` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.avg_grade_adjusted_speed` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m/s, scope: stored)*
- `activity.body_battery_start` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.cadence_drop_pct` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: %, scope: stored)*
- `activity.calories` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: kcal, scope: stored)*
- `activity.decoupling_data_quality_score` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*
- `activity.decoupling_reason_if_unsuitable` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.decoupling_suitability_flag` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.distance` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m, scope: stored)*
- `activity.distance_m` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m, scope: stored)*
- `activity.duration` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: %, scope: stored)*
- `activity.duration_s` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: s, scope: stored)*
- `activity.ef_drop_pct` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: %, scope: stored)*
- `activity.efficiency_data_quality` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.elapsed_duration` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: %, scope: stored)*
- `activity.grade_adjusted_speed_mps` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m/s, scope: stored)*
- `activity.ground_contact_time` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: s, scope: stored)*
- `activity.has_detailed_data` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.humidity` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.intensity_factor` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.lactate_threshold_heart_rate` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: bpm, scope: stored)*
- `activity.lactate_threshold_speed` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m/s, scope: stored)*
- `activity.max_elevation` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m, scope: stored)*
- `activity.max_heart_rate` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: bpm, scope: stored)*
- `activity.max_power` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: W, scope: stored)*
- `activity.max_running_cadence` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.max_speed` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m/s, scope: stored)*
- `activity.median_efficiency_factor` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.min_available_stamina` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*
- `activity.min_elevation` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m, scope: stored)*
- `activity.min_heart_rate` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: bpm, scope: stored)*
- `activity.moving_duration` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: %, scope: stored)*
- `activity.negative_split_percent` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: %, scope: stored)*
- `activity.pace_drop_pct` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: %, scope: stored)*
- `activity.pace_sec_per_km` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: s/km, scope: stored)*
- `activity.recovery_time` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: s, scope: stored)*
- `activity.running_economy` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.steady_state_efficiency_factor` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.temperature` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: C, scope: stored)*
- `activity.total_anaerobic_training_effect` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*
- `activity.total_descent` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m, scope: stored)*
- `activity.total_steps` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.total_training_effect` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*
- `activity.training_effect_label` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*
- `activity.weather_condition` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: value, scope: stored)*
- `activity.wind_speed` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m/s, scope: stored)*

#### `aerobic_efficiency` (2 nøkler)

- `activity.decoupling_percent` — Prosent fall i efficiency factor fra 1. til 2. halvdel av økten. *(enhet: %, scope: stored)*
- `activity.hr_drift_pct` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: %, scope: stored)*

#### `fatigue` (1 nøkler)

- `activity.fatigue_resistance_score` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*

#### `garmin_performance` (31 nøkler)

- `performance.acwr_status` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.acwr_status_feedback` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.altitude_trend` — Garmin performance status (VO2, load balance, scores). *(enhet: m, scope: stored)*
- `performance.current_altitude` — Garmin performance status (VO2, load balance, scores). *(enhet: m, scope: stored)*
- `performance.daily_acute_chronic_workload_ratio` — Garmin performance status (VO2, load balance, scores). *(enhet: %, scope: stored)*
- `performance.endurance_classification` — Garmin performance status (VO2, load balance, scores). *(enhet: value, scope: stored)*
- `performance.fitness_age` — Garmin performance status (VO2, load balance, scores). *(enhet: value, scope: stored)*
- `performance.fitness_trend` — Garmin performance status (VO2, load balance, scores). *(enhet: value, scope: stored)*
- `performance.fitness_trend_sport` — Garmin performance status (VO2, load balance, scores). *(enhet: value, scope: stored)*
- `performance.heat_acclimation_percentage` — Garmin performance status (VO2, load balance, scores). *(enhet: %, scope: stored)*
- `performance.heat_trend` — Garmin performance status (VO2, load balance, scores). *(enhet: value, scope: stored)*
- `performance.hill_endurance_score` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.hill_strength_score` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.load_tunnel_max` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.load_tunnel_min` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.max_met_category` — Garmin performance status (VO2, load balance, scores). *(enhet: value, scope: stored)*
- `performance.monthly_load_aerobic_high` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.monthly_load_aerobic_high_target_max` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.monthly_load_aerobic_high_target_min` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.monthly_load_aerobic_low` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.monthly_load_aerobic_low_target_max` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.monthly_load_aerobic_low_target_min` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.monthly_load_anaerobic` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.monthly_load_anaerobic_target_max` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.monthly_load_anaerobic_target_min` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.previous_altitude_acclimation` — Garmin performance status (VO2, load balance, scores). *(enhet: m, scope: stored)*
- `performance.previous_heat_acclimation_percentage` — Garmin performance status (VO2, load balance, scores). *(enhet: %, scope: stored)*
- `performance.sport` — Garmin performance status (VO2, load balance, scores). *(enhet: value, scope: stored)*
- `performance.sub_sport` — Garmin performance status (VO2, load balance, scores). *(enhet: value, scope: stored)*
- `performance.training_balance_feedback_phrase` — Garmin performance status (VO2, load balance, scores). *(enhet: value, scope: stored)*
- `performance.training_status_feedback_phrase` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*

#### `garmin_score` (2 nøkler)

- `performance.endurance_score` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.hill_score` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*

#### `health_hrv` (12 nøkler)

- `hrv.baseline_balanced_lower` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `hrv.baseline_balanced_upper` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `hrv.baseline_low_upper` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `hrv.breathing_rate` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `hrv.heart_rate` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: bpm, scope: stored)*
- `hrv.measurement_duration` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `hrv.measurement_quality` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `hrv.measurement_type` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `hrv.pnn50` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `hrv.rmssd` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `hrv.status` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: score, scope: stored)*
- `hrv.stress_score` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: score, scope: stored)*

#### `health_recovery` (11 nøkler)

- `body_battery.body_battery_charged` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `body_battery.body_battery_charged_start` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `body_battery.body_battery_drained` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `body_battery.body_battery_drained_start` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `body_battery.max_body_battery` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `body_battery.min_body_battery` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `body_battery.net_charge` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `resting_heart_rate.confidence_level` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `resting_heart_rate.measurement_method` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `resting_heart_rate.measurement_quality` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `resting_heart_rate.resting_heart_rate` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: bpm, scope: stored)*

#### `health_sleep` (26 nøkler)

- `sleep.average_heart_rate` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: bpm, scope: stored)*
- `sleep.average_respiration_rate` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `sleep.average_spo2` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `sleep.awake_percent` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `sleep.awake_time` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s, scope: stored)*
- `sleep.deep_sleep_percent` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `sleep.deep_sleep_time` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s, scope: stored)*
- `sleep.heart_rate_variability` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: bpm, scope: stored)*
- `sleep.highest_heart_rate` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: bpm, scope: stored)*
- `sleep.light_sleep_percent` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `sleep.light_sleep_time` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s, scope: stored)*
- `sleep.lowest_heart_rate` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: bpm, scope: stored)*
- `sleep.lowest_spo2` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `sleep.movement_score` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: score, scope: stored)*
- `sleep.overall_score` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: score, scope: stored)*
- `sleep.recovery_score` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: score, scope: stored)*
- `sleep.rem_sleep_percent` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `sleep.rem_sleep_time` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s, scope: stored)*
- `sleep.restless_moments` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `sleep.sleep_efficiency` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `sleep.sleep_latency` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `sleep.sleep_quality` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `sleep.sleep_score` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: score, scope: stored)*
- `sleep.stress_score` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: score, scope: stored)*
- `sleep.total_sleep_time` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s, scope: stored)*
- `sleep.wake_episodes` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*

#### `health_stress` (9 nøkler)

- `stress.activity_stress_duration` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `stress.data_quality` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `stress.high_stress_time` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s, scope: stored)*
- `stress.low_stress_time` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s, scope: stored)*
- `stress.medium_stress_time` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s, scope: stored)*
- `stress.rest_time` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s, scope: stored)*
- `stress.stress_level` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `stress.stress_time` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s, scope: stored)*
- `stress.total_time` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s, scope: stored)*

#### `hrv` (1 nøkler)

- `health.hrv_rmssd` — Daglig helsemetric (søvn, HRV, puls, body battery). *(enhet: ms, scope: stored)*

#### `load_balance` (3 nøkler)

- `performance.load_aerobic_high` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.load_aerobic_low` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.load_anaerobic` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*

#### `performance` (4 nøkler)

- `activity.vo2_max` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: ml/kg/min, scope: stored)*
- `activity.vo2_max_precise` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: ml/kg/min, scope: stored)*
- `performance.vo2_max` — Garmin performance status (VO2, load balance, scores). *(enhet: ml/kg/min, scope: stored)*
- `performance.vo2_max_precise` — Garmin performance status (VO2, load balance, scores). *(enhet: ml/kg/min, scope: stored)*

#### `power` (2 nøkler)

- `activity.average_power` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: W, scope: stored)*
- `activity.normalized_power` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: W, scope: stored)*

#### `readiness` (1 nøkler)

- `activity.training_readiness_score` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*

#### `recovery` (5 nøkler)

- `activity.body_battery_delta` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*
- `health.body_battery_max` — Daglig helsemetric (søvn, HRV, puls, body battery). *(enhet: score, scope: stored)*
- `health.body_battery_min` — Daglig helsemetric (søvn, HRV, puls, body battery). *(enhet: score, scope: stored)*
- `health.body_battery_net_charge` — Daglig helsemetric (søvn, HRV, puls, body battery). *(enhet: score, scope: stored)*
- `health.resting_heart_rate` — Daglig helsemetric (søvn, HRV, puls, body battery). *(enhet: bpm, scope: stored)*

#### `route` (26 nøkler)

- `route_fingerprint.bbox_max_latitude` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_fingerprint.bbox_max_longitude` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_fingerprint.bbox_min_latitude` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_fingerprint.bbox_min_longitude` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_fingerprint.centroid_latitude` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_fingerprint.centroid_longitude` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_fingerprint.end_latitude` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_fingerprint.end_longitude` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_fingerprint.gps_point_count` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: count, scope: stored)*
- `route_fingerprint.method_version` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_fingerprint.point_count` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: count, scope: stored)*
- `route_fingerprint.quality_score` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: score, scope: stored)*
- `route_fingerprint.route_distance_m` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `route_fingerprint.sampled_point_count` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: count, scope: stored)*
- `route_fingerprint.start_latitude` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_fingerprint.start_longitude` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_match.distance_ratio` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `route_match.end_distance_m` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `route_match.mean_distance_m` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `route_match.method_version` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_match.overlap_quality` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_match.p90_distance_m` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `route_match.reverse_direction` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_match.same_route` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `route_match.similarity_score` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: score, scope: stored)*
- `route_match.start_distance_m` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*

#### `running_dynamics` (4 nøkler)

- `activity.average_running_cadence` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: spm, scope: stored)*
- `activity.stride_length` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m, scope: stored)*
- `activity.vertical_oscillation` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: cm, scope: stored)*
- `activity.vertical_ratio` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: %, scope: stored)*

#### `sleep` (3 nøkler)

- `health.sleep_duration_s` — Daglig helsemetric (søvn, HRV, puls, body battery). *(enhet: s, scope: stored)*
- `health.sleep_overall_score` — Daglig helsemetric (søvn, HRV, puls, body battery). *(enhet: score, scope: stored)*
- `health.sleep_score` — Daglig helsemetric (søvn, HRV, puls, body battery). *(enhet: score, scope: stored)*

#### `stamina` (2 nøkler)

- `activity.begin_potential_stamina` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*
- `activity.end_potential_stamina` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*

#### `stress` (2 nøkler)

- `health.high_stress_time_s` — Daglig helsemetric (søvn, HRV, puls, body battery). *(enhet: s, scope: stored)*
- `health.stress_level` — Daglig helsemetric (søvn, HRV, puls, body battery). *(enhet: score, scope: stored)*

#### `summary` (85 nøkler)

- `daily_summary.avg_cadence` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `daily_summary.avg_heart_rate` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: bpm, scope: stored)*
- `daily_summary.avg_pace` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s/km, scope: stored)*
- `daily_summary.avg_speed` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m/s, scope: stored)*
- `daily_summary.best_distance` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `daily_summary.best_duration` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `daily_summary.best_pace` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s/km, scope: stored)*
- `daily_summary.best_speed` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m/s, scope: stored)*
- `daily_summary.total_activities` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `daily_summary.total_ascent` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `daily_summary.total_calories` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: kcal, scope: stored)*
- `daily_summary.total_descent` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `daily_summary.total_distance` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `daily_summary.total_duration` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `monthly_summary.activities_per_day` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `monthly_summary.activities_per_week` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `monthly_summary.activities_trend` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `monthly_summary.avg_cadence` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `monthly_summary.avg_heart_rate` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: bpm, scope: stored)*
- `monthly_summary.avg_pace` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s/km, scope: stored)*
- `monthly_summary.avg_speed` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m/s, scope: stored)*
- `monthly_summary.best_distance` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `monthly_summary.best_duration` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `monthly_summary.best_pace` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s/km, scope: stored)*
- `monthly_summary.best_speed` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m/s, scope: stored)*
- `monthly_summary.distance_per_day` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `monthly_summary.distance_per_week` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `monthly_summary.distance_trend` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `monthly_summary.duration_per_day` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `monthly_summary.duration_per_week` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `monthly_summary.duration_trend` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `monthly_summary.month` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: count, scope: stored)*
- `monthly_summary.total_activities` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `monthly_summary.total_ascent` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `monthly_summary.total_calories` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: kcal, scope: stored)*
- `monthly_summary.total_descent` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `monthly_summary.total_distance` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `monthly_summary.total_duration` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `monthly_summary.total_tss` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `monthly_summary.year` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: count, scope: stored)*
- `weekly_summary.activities_per_day` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `weekly_summary.avg_cadence` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `weekly_summary.avg_heart_rate` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: bpm, scope: stored)*
- `weekly_summary.avg_pace` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s/km, scope: stored)*
- `weekly_summary.avg_speed` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m/s, scope: stored)*
- `weekly_summary.best_distance` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `weekly_summary.best_duration` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `weekly_summary.best_pace` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s/km, scope: stored)*
- `weekly_summary.best_speed` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m/s, scope: stored)*
- `weekly_summary.distance_per_day` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `weekly_summary.duration_per_day` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `weekly_summary.total_activities` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `weekly_summary.total_ascent` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `weekly_summary.total_calories` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: kcal, scope: stored)*
- `weekly_summary.total_descent` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `weekly_summary.total_distance` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `weekly_summary.total_duration` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `weekly_summary.week_number` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: count, scope: stored)*
- `weekly_summary.year` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: count, scope: stored)*
- `yearly_summary.activities_per_day` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `yearly_summary.activities_per_month` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `yearly_summary.activities_per_week` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `yearly_summary.activities_trend` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `yearly_summary.avg_cadence` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `yearly_summary.avg_heart_rate` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: bpm, scope: stored)*
- `yearly_summary.avg_pace` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s/km, scope: stored)*
- `yearly_summary.avg_speed` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m/s, scope: stored)*
- `yearly_summary.best_distance` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `yearly_summary.best_duration` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `yearly_summary.best_pace` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: s/km, scope: stored)*
- `yearly_summary.best_speed` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m/s, scope: stored)*
- `yearly_summary.distance_per_day` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `yearly_summary.distance_per_month` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `yearly_summary.distance_per_week` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `yearly_summary.distance_trend` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `yearly_summary.duration_per_day` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `yearly_summary.duration_per_month` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `yearly_summary.duration_per_week` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `yearly_summary.duration_trend` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*
- `yearly_summary.total_activities` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `yearly_summary.total_ascent` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `yearly_summary.total_calories` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: kcal, scope: stored)*
- `yearly_summary.total_descent` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `yearly_summary.total_distance` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m, scope: stored)*
- `yearly_summary.total_duration` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: %, scope: stored)*

#### `terrain` (1 nøkler)

- `activity.total_ascent` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: m, scope: stored)*

#### `threshold` (6 nøkler)

- `lactate_threshold.is_fallback` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `lactate_threshold.lactate_threshold_heart_rate` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: bpm, scope: stored)*
- `lactate_threshold.lactate_threshold_speed` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m/s, scope: stored)*
- `lactate_threshold.raw_lactate_threshold_speed` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: m/s, scope: stored)*
- `lactate_threshold.source` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*
- `lactate_threshold.sync_context` — Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope. *(enhet: value, scope: stored)*

#### `training_effect` (2 nøkler)

- `activity.aerobic_training_effect` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*
- `activity.anaerobic_training_effect` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*

#### `training_load` (5 nøkler)

- `activity.epoc` — Verdi fra én synkronisert Garmin/FIT-aktivitet. *(enhet: score, scope: stored)*
- `activity.training_stress_score` — Belastningsscore per økt (≈ EPOC fra Garmin der tilgjengelig). *(enhet: score, scope: stored)*
- `performance.acwr_percent` — Garmin performance status (VO2, load balance, scores). *(enhet: %, scope: stored)*
- `performance.daily_training_load_acute` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*
- `performance.daily_training_load_chronic` — Garmin performance status (VO2, load balance, scores). *(enhet: score, scope: stored)*

#### `training_status` (1 nøkler)

- `performance.training_status` — Garmin performance status (VO2, load balance, scores). *(enhet: code, scope: stored)*

---

## MCP-oppslag

| Kanal | Bruk |
|-------|------|
| Ressurs `treningsanalyse://metric-glossary` | Full JSON-ordbok |
| Verktøy `metric_glossary(metric_key=...)` | Én metrikk eller søk |
| Verktøy `metric_catalog()` | Alle nøkler + kort `summary` |
| Verktøy `query_metric_timeseries(...)` | Verdidata |
