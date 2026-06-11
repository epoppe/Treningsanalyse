"""Ordbok for MCP-metrikker — brukes av agenter for presis coaching."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Viktig å skille disse når du coacher
COACHING_DISAMBIGUATION: List[Dict[str, str]] = [
    {
        "topic": "Readiness",
        "metrics": "readiness.total_score vs readiness_score",
        "rule": (
            "readiness.total_score er Garmin-modellen (søvn 15 %, HRV 15 %, form/TSB 70 %) "
            "fra daglig-readiness. readiness_score er en intern coaching-heuristikk "
            "(recovery + Banister-form). Ikke bruk dem om hverandre."
        ),
    },
    {
        "topic": "Belastning",
        "metrics": "fitness.ctl / fitness.atl / fitness.tsb vs load.acwr",
        "rule": (
            "CTL/ATL/TSB beregnes fra TSS/EPOC i lokale data. load.acwr kommer fra Garmin "
            "der tilgjengelig. Begge beskriver belastning, men med ulik kilde."
        ),
    },
    {
        "topic": "Soner",
        "metrics": "coaching.zone1_pct–3 vs training.class_1_pct–8",
        "rule": (
            "coaching.zone* er Seiler 80/20 (lav / threshold / høy) basert på LT1/LT2. "
            "training.class_* er 8 finere klasser (recovery → race). Bruk zone* for "
            "polarisert analyse og class_* for detaljert intensitetsfordeling."
        ),
    },
    {
        "topic": "Duration curve",
        "metrics": "running.speed_5m vs running.speed_5m_hist",
        "rule": (
            "Uten _hist: beste verdi i nåværende snapshot (typisk all-time). "
            "Med _hist: rullerende 365-dagers beste per dag — bruk for utvikling over tid."
        ),
    },
    {
        "topic": "Performance driver",
        "metrics": "performance_driver_name",
        "rule": (
            "Navngir sterkest negativ faktor akkurat nå (HRV, søvn, belastning, TSB, …). "
            "Er en vektet heuristikk, ikke en Garmin-diagnose."
        ),
    },
]

SCOPE_DESCRIPTIONS: Dict[str, str] = {
    "stored": "Verdi lagret i database per aktivitet eller døgn (Garmin/sync).",
    "daily": "Beregnet én verdi per kalenderdag.",
    "activity": "Én verdi per treningsøkt.",
    "snapshot": "Én gjeldende verdi (typisk siste beregning / all-time).",
    "rolling_daily": "Daglig verdi basert på rullerende vindu (f.eks. 365 dager tilbake).",
}

CATEGORY_GLOSSARY: Dict[str, Dict[str, str]] = {
    "activity": {
        "definition": "Rå eller Garmin-beregnet verdi knyttet til én treningsøkt.",
        "coaching_use": "Bruk for konkret øktanalyse, ikke for langsiktig trend uten aggregat.",
    },
    "training_load": {
        "definition": "Akutt/kronisk belastning og risiko for monotoni.",
        "coaching_use": "Vurder om volum og intensitet er bærekraftig denne uken.",
    },
    "readiness": {
        "definition": "Dagsform basert på søvn, HRV og treningsbalanse (Garmin-modell).",
        "coaching_use": "Anbefal hard / moderat / lett / hvile for dagens økt.",
    },
    "coaching": {
        "definition": "Interne heuristiske scorer og drivere — ikke offisielle Garmin-score.",
        "coaching_use": "Suppler Garmin-data; merk alltid at det er modellert.",
    },
    "running": {
        "definition": "Løpsprestasjon, kurver og økonomi fra FIT/effort-data.",
        "coaching_use": "Kapasitet, fart over varighet, og aerob effektivitet.",
    },
    "cardio": {
        "definition": "HRV, puls og aerob drift over tid.",
        "coaching_use": "Recovery-trend og tegn på stress/utmattelse.",
    },
    "recovery": {
        "definition": "HRV-baseline, recovery-score og predikert tid til baseline.",
        "coaching_use": "Forklar hvorfor hard trening bør utsettes eller tones ned.",
    },
    "fitness": {
        "definition": "CTL/ATL/TSB og aerob effektivitet (EF) fra lokal TSS-modell.",
        "coaching_use": "Form, fitness og om athlete er fresh eller sliten.",
    },
    "sleep": {
        "definition": "Søvnlengde, kvalitet og akkumulert søvngjeld.",
        "coaching_use": "Koble dårlig søvn til anbefalt intensitet neste dag.",
    },
    "risk": {
        "definition": "Heuristiske risikoscore for overtrening og skade.",
        "coaching_use": "Advar ved høye verdier; ikke bruk som medisinsk diagnose.",
    },
    "route": {
        "definition": "Sammenligning med tidligere økter på samme rute.",
        "coaching_use": "Objektiv progresjon uavhengig av vær og dagsform.",
    },
    "weather": {
        "definition": "Temperaturjustert pace og estimert prestasjonstap.",
        "coaching_use": "Normaliser langsomme økter i varme/kulde.",
    },
    "performance": {
        "definition": "VO2, predikerte løpstider og Garmin performance-felter.",
        "coaching_use": "Kapasitet og målsetting — prediksjoner er modellbaserte.",
    },
    "training": {
        "definition": "Intensitetsfordeling og treningsklasser.",
        "coaching_use": "80/20, soner og om hard trening dominerer.",
    },
}

# Eksplisitte oppføringer for alle derived + viktige lagrede nøkler
METRIC_GLOSSARY: Dict[str, Dict[str, Any]] = {
    "consistency.score": {
        "title": "Training Consistency Score",
        "definition": "Andel av siste 28 dager med minst én løpeøkt (0–100).",
        "interpretation": "85+ svært bra, 70–85 bra, under 60 inkonsistent.",
        "coaching_use": "Vurder om fremgang stoppes av hull i treningen, ikke bare CTL.",
        "source": "computed",
    },
    "fitness.gain_rate": {
        "title": "Fitness gain rate (CTL)",
        "definition": "Endring i CTL per dag over siste 42 dager.",
        "interpretation": "Positiv = bygger form; negativ = taper eller sykdom.",
        "coaching_use": "Retning viktigere enn dagens CTL-nivå.",
        "source": "computed",
    },
    "coaching.polarization_score": {
        "title": "Polarization score",
        "definition": "Hvor nær 80/20-fordeling (lav/høy) brukeren er.",
        "interpretation": "100 = ideell polarisert profil siste 28 dager.",
        "coaching_use": "Juster volum mot rolig vs hard trening.",
        "source": "computed",
    },
    "running.durability_score": {
        "title": "Durability score",
        "definition": "Evnen til å holde prestasjon på langkjøringer (drift, fatigue resistance).",
        "interpretation": "Høyere = bedre utholdenhet sent i lange økter.",
        "coaching_use": "Maraton/HM-planlegging og langtur-kvalitet.",
        "source": "computed",
    },
    "readiness.5k": {
        "title": "Event readiness 5K",
        "definition": "Konkurransespesifikk readiness 0–100 for 5 km.",
        "interpretation": "Kombinerer Garmin readiness, TSB, HRV og søvn for kort race.",
        "coaching_use": "Anbefal start eller utsettelse av 5K/10K.",
        "source": "heuristic",
    },
    "coaching.recommended_workout": {
        "title": "Anbefalt neste økt",
        "definition": "Enum: rest, recovery_run, easy_run, threshold, vo2_intervals, long_run, …",
        "interpretation": "Samlet anbefaling fra readiness, belastning og treningsfase.",
        "coaching_use": "Konkret «hva bør du gjøre i dag».",
        "source": "heuristic",
    },

  "readiness.total_score": {
    "title": "Garmin training readiness (total)",
    "definition": "Samlet dags-score 0–100 fra TrainingReadinessService (søvn, HRV, form).",
    "interpretation": "Høyere er bedre. Under ~50: vurder lett økt. Under ~35: hvile.",
    "coaching_use": "Primær readiness for «kan jeg trene hardt i dag?»",
    "caveats": "Ikke forveksle med readiness_score (coaching-heuristikk).",
    "source": "computed_garmin_model",
  },
  "activity.body_battery_delta": {
    "title": "Body Battery endring (aktivitet)",
    "definition": "Endring i Body Battery gjennom aktiviteten (summaryDTO.differenceBodyBattery).",
    "interpretation": "Negativ = tap; positiv = netto lading under økta (sjeldent ved hard trening).",
    "coaching_use": "Koble belastning til recovery-kostnad samme dag.",
    "caveats": "Samme kolonne som activity.activity_body_battery_delta.",
    "source": "garmin_sync",
  },
  "health.hrv_rmssd": {
    "title": "HRV RMSSD (natt)",
    "definition": "Root mean square of successive differences — nattlig HRV fra Garmin/sync.",
    "interpretation": "Sammenlign mot egen baseline; enkeltdag er støy.",
    "coaching_use": "Recovery-trend; bruk recovery_context.hrv eller cardio.hrv_7d for kontekst.",
    "source": "garmin_sync",
  },
  "readiness.sleep_component": {
    "title": "Readiness — søvn",
    "definition": "Søvnkomponent (0–100) i Garmin readiness-modellen.",
    "interpretation": "Lav verdi tyder på utilstrekkelig eller dårlig søvn siste netter.",
    "coaching_use": "Forklar hvorfor rolig dag anbefales selv om athlete «føler seg ok».",
    "source": "computed_garmin_model",
  },
  "readiness.hrv_component": {
    "title": "Readiness — HRV",
    "definition": "HRV-komponent (0–100) basert på nylig RMSSD vs baseline.",
    "interpretation": "Lav score = autonom stress eller incomplete recovery.",
    "coaching_use": "Bruk sammen med recovery.hrv_delta_pct for narrativ.",
    "source": "computed_garmin_model",
  },
  "readiness.form_component": {
    "title": "Readiness — form (TSB)",
    "definition": "Form/TSB normalisert til 0–100 (tung vekt i total score).",
    "interpretation": "Reflekterer CTL−ATL; lav score = høy akutt tretthet.",
    "coaching_use": "Koble til fitness.tsb når du forklarer belastning.",
    "source": "computed_garmin_model",
  },
  "readiness_score": {
    "title": "Coaching readiness (heuristikk)",
    "definition": "Intern score fra recovery + Banister-form — ikke Garmin.",
    "interpretation": "0–100, høyere = bedre dagsform i coaching-modellen.",
    "coaching_use": "Kun når du eksplisitt bruker coaching-modellen, ikke Garmin UI.",
    "caveats": "Erstatter ikke readiness.total_score.",
    "source": "heuristic",
  },
  "fitness.ctl": {
    "title": "Chronic Training Load (CTL)",
    "definition": "42-dagers eksponentiell glidende snitt av daglig TSS/EPOC.",
    "interpretation": "Høyere = mer kronisk treningsvolum (fitness). Stiger sakte.",
    "coaching_use": "Beskriv langsiktig treningsstatus og kapasitet.",
    "source": "computed_tss",
  },
  "fitness.atl": {
    "title": "Acute Training Load (ATL)",
    "definition": "7-dagers eksponentiell glidende snitt av daglig TSS/EPOC.",
    "interpretation": "Reagerer raskt på nylige harde økter.",
    "coaching_use": "Forklar «hvor sliten er du nå» vs CTL (fitness).",
    "source": "computed_tss",
  },
  "fitness.tsb": {
    "title": "Training Stress Balance (TSB / Form)",
    "definition": "CTL minus ATL. Positiv = relativt fresh, negativ = akkumulert fatigue.",
    "interpretation": "Omtrent −10 til +10 er ofte normalt i opplæring; svært negativ = risiko.",
    "coaching_use": "Kjerne for taper, overreaching og restitusjonsdager.",
    "source": "computed_tss",
  },
  "fitness.form": {
    "title": "Form (alias TSB)",
    "definition": "Samme som fitness.tsb.",
    "interpretation": "Se fitness.tsb.",
    "coaching_use": "Se fitness.tsb.",
    "source": "computed_tss",
  },
  "fitness.ef_30d": {
    "title": "Aerob effektivitet (30 dager)",
    "definition": "Rullerende snitt av speed/HR (m/s per bpm) på rolige økter.",
    "interpretation": "Høyere = bedre økonomi ved lav intensitet over tid.",
    "coaching_use": "Trend for aerob utvikling — sammenlign over uker, ikke én økt.",
    "source": "computed",
  },
  "load.acwr": {
    "title": "Acute:Chronic Workload Ratio",
    "definition": "Akutt/kronisk belastningsforhold (Garmin eller coaching-fallback).",
    "interpretation": "~0.8–1.3 ofte trygt; >1.5 øker skaderisiko i litteraturen.",
    "coaching_use": "Advar ved brå økning i belastning.",
    "source": "garmin_or_computed",
  },
  "load.monotony": {
    "title": "Treningsmonotoni",
    "definition": "Snitt belastning / standardavvik siste 7 dager.",
    "interpretation": "Høy monotoni = lite variasjon dag til dag.",
    "coaching_use": "Anbefal variasjon eller hviledag ved høy monotoni + høy strain.",
    "source": "computed",
  },
  "load.strain": {
    "title": "Treningsstrain",
    "definition": "Ukes sum TSS multiplisert med monotoni.",
    "interpretation": "Høy strain = mye volum med lite variasjon.",
    "coaching_use": "Kombiner med monotony for overtreningssignal.",
    "source": "computed",
  },
  "recovery.predicted_hours_to_baseline": {
    "title": "Predikert timer til baseline",
    "definition": "Heuristisk estimat (6–120 t) før readiness/TSB normaliseres.",
    "interpretation": "Høyere = mer hvile anbefales før hard økt.",
    "coaching_use": "Konkret «vent X timer» — merk at det er estimat, ikke Garmin.",
    "caveats": "PPAP fase 3-heuristikk, ikke klinisk validert.",
    "source": "heuristic",
  },
  "coaching.zone1_pct": {
    "title": "Lav intensitet (soner 1)",
    "definition": "Andel økttid under LT1 (Seiler lav sone).",
    "interpretation": "Mål ~75–85 % for polarisert 80/20.",
    "coaching_use": "Flagg for lite rolig volum.",
    "source": "computed_lt",
  },
  "coaching.zone2_pct": {
    "title": "Threshold-sone (soner 2)",
    "definition": "Andel tid mellom LT1 og LT2.",
    "interpretation": "Bør typisk være lav (<15 %) i polarisert modell.",
    "coaching_use": "Advar ved «grå sone»-dominans.",
    "source": "computed_lt",
  },
  "coaching.zone3_pct": {
    "title": "Høy intensitet (soner 3)",
    "definition": "Andel tid over LT2.",
    "interpretation": "Noen få prosent er ofte nok; for mye øker fatigue.",
    "coaching_use": "Balanser med zone1_pct.",
    "source": "computed_lt",
  },
  "training.training_zone": {
    "title": "3-sones sone (per økt)",
    "definition": "1=under LT1, 2=mellom LT1–LT2, 3=over LT2 (snittpuls).",
    "interpretation": "Grov klassifisering per aktivitet.",
    "coaching_use": "Rask øktklassifisering — bruk class_* for finfordeling.",
    "source": "computed_lt",
  },
  "training.training_class": {
    "title": "8-klassers sone (per økt)",
    "definition": "1=recovery … 8=race, basert på puls vs LT1/LT2.",
    "interpretation": "Hele tall 1–8.",
    "coaching_use": "Detaljert intensitet på enkeltøkter.",
    "source": "computed_lt",
  },
  "performance_driver_name": {
    "title": "Sterkest negativ driver",
    "definition": "Faktornavn med høyest vektet avvik (HRV, søvn, belastning, …).",
    "interpretation": "Tekstlabel, ikke numerisk score.",
    "coaching_use": "Start coaching-svar med «hovedårsak akkurat nå er …»",
    "source": "heuristic_ml",
  },
  "performance_driver_weight": {
    "title": "Driver-vekt",
    "definition": "Normalisert andel (0–1) av hvor mye den valgte driveren dominerer.",
    "interpretation": "Høyere = mer relevant å adressere først.",
    "coaching_use": "Prioriter tiltak etter vekt.",
    "source": "heuristic_ml",
  },
  "running.critical_speed": {
    "title": "Critical Speed",
    "definition": "CS fra hyperbolsk modell (m/s) på beste speed-efforts siste ~365 d.",
    "interpretation": "Høyere = bedre aerob/anaerob kapasitet.",
    "coaching_use": "Kapasitet og pacing for intervaller.",
    "source": "computed_fit",
  },
  "running.w_prime": {
    "title": "W′ (anaerob kapasitet)",
    "definition": "Skjærepunkt D′ fra CS-modell (meter).",
    "interpretation": "Større W′ = mer «kick» over CS.",
    "coaching_use": "Forklar kort, hard innsats vs lang distanse.",
    "source": "computed_fit",
  },
  "running.speed_5m": {
    "title": "Beste 5-min fart (snapshot)",
    "definition": "Beste gjennomsnittsfart over 5 min i snapshot-vindu (typisk all-time).",
    "interpretation": "m/s — høyere er raskere.",
    "coaching_use": "VO2-aktig kapasitet — sammenlign med hist for trend.",
    "source": "computed_fit",
  },
  "running.speed_5m_hist": {
    "title": "Beste 5-min fart (365d rullerende)",
    "definition": "Per dag: beste 5-min fart fra efforts siste 365 dager.",
    "interpretation": "Stigende trend = forbedret kort fart.",
    "coaching_use": "Historisk utvikling — foretrekk over snapshot i trendanalyse.",
    "source": "computed_fit",
  },
  "cardio.hrv_7d": {
    "title": "HRV 7-dagers snitt",
    "definition": "Snitt RMSSD siste 7 dager.",
    "interpretation": "Sammenlign med baseline og recovery.hrv_baseline.",
    "coaching_use": "Kort trend — ikke overtolking av én dag.",
    "source": "stored_hrv",
  },
  "recovery.hrv_delta_pct": {
    "title": "HRV avvik fra baseline (%)",
    "definition": "Prosentvis avvik RMSSD vs 28-dagers baseline.",
    "interpretation": "Negativ = under normal — ofte tegn på stress/fatigue.",
    "coaching_use": "Forklar readiness og hvile anbefaling.",
    "source": "computed",
  },
  "activity.decoupling_percent": {
    "title": "Aerobic decoupling",
    "definition": "Prosent fall i efficiency factor fra 1. til 2. halvdel av økten.",
    "interpretation": "Positiv = mer puls per fart sent i økta (aerob stress).",
    "coaching_use": "Kun på steady-state økter >45 min; se suitability-flagg.",
    "source": "computed_fit",
  },
  "activity.grade_adjusted_pace_sec_per_km": {
    "title": "Grade Adjusted Pace (GAP)",
    "definition": (
      "Garmin sin stigningsjusterte snittfart (avgGradeAdjustedSpeed), lagret som m/s "
      "i activities.avg_grade_adjusted_speed og eksponert som M:SS/km."
    ),
    "interpretation": (
      "Lavere pace enn rå snittfart på kupert terreng; mangler ofte på flate, innendørs "
      "eller ikke-løpsaktiviteter. Kan ikke beregnes lokalt uten Garmins modell."
    ),
    "coaching_use": "Sammenlign faktisk innsats på bakke mot flat pace og terskelfart.",
    "source": "garmin_sync",
  },
    "activity.training_stress_score": {
        "title": "Training Stress Score (TSS)",
        "definition": "Belastningsscore per økt (≈ EPOC fra Garmin der tilgjengelig).",
        "interpretation": "100 ≈ 1 time ved terskel; summeres til CTL/ATL.",
        "coaching_use": "Volum og intensitet per uke.",
        "source": "garmin_or_estimated",
    },
    "health.hrv_rmssd": {
        "title": "HRV RMSSD (natt)",
        "definition": "Rå RMSSD fra siste natt-måling (ms) — kanonisk lagret HRV-nøkkel.",
        "interpretation": "Sammenlign med recovery.hrv_baseline og recovery.hrv_delta_pct for trend.",
        "coaching_use": "Daglig recovery; bruk cardio.hrv_7d for kort glidende snitt.",
        "source": "garmin_sync",
    },
}

# Fyll inn training.class_N_pct og duration curve-varianter programmatisk
_CLASS_LABELS_NO = (
    "Recovery",
    "Lett",
    "Aerob",
    "Tempo",
    "Threshold",
    "VO2",
    "Anaerob",
    "Race",
)
for i, label in enumerate(_CLASS_LABELS_NO, start=1):
    METRIC_GLOSSARY[f"training.class_{i}_pct"] = {
        "title": f"Treningsklasse {i} ({label}) — andel tid",
        "definition": f"Andel økttid klassifisert som {label} siste 28 dager.",
        "interpretation": "Prosent av total løpetid; summer til ~100 %.",
        "coaching_use": "Finfordeling utover 3-soners coaching.zone*.",
        "source": "computed_lt",
    }

_DURATION_LABELS = {
    "30s": "30 sekunder",
    "1m": "1 minutt",
    "3m": "3 minutter",
    "5m": "5 minutter",
    "10m": "10 minutter",
    "20m": "20 minutter",
    "30m": "30 minutter",
    "40m": "40 minutter",
    "60m": "60 minutter",
}
for dur_key, dur_label in _DURATION_LABELS.items():
    for kind, unit, name in (
        ("speed", "m/s", "fart"),
        ("power", "W", "effekt"),
    ):
        base = f"running.{kind}_{dur_key}"
        METRIC_GLOSSARY[base] = {
            "title": f"Beste {dur_label} {name} (snapshot)",
            "definition": f"Beste gjennomsnittlig {name} over {dur_label} i snapshot (ofte all-time).",
            "interpretation": f"Høyere {unit} = bedre for den varigheten.",
            "coaching_use": "Kapasitetspunkt på duration curve.",
            "source": "computed_fit",
        }
        METRIC_GLOSSARY[f"{base}_hist"] = {
            "title": f"Beste {dur_label} {name} (365d rullerende)",
            "definition": f"Per dag: beste {name} over {dur_label} fra siste 365 dager.",
            "interpretation": "Bruk for trend — ikke sammenlign direkte med snapshot uten kontekst.",
            "coaching_use": "Historisk utvikling på duration curve.",
            "source": "computed_fit",
        }

# Utvid med generiske coaching-/risiko-/søvn-derived der ikke allerede definert
_GENERIC_DERIVED: Dict[str, Dict[str, Any]] = {
    "fitness_score": {
        "title": "Fitness score (coaching)",
        "definition": "Normalisert Banister-fitness (0–100).",
        "interpretation": "Høyere = høyere kronisk fitness i modellen.",
        "coaching_use": "Forenklet fitness for narrativ.",
        "source": "heuristic",
    },
    "fatigue_score": {
        "title": "Fatigue score (coaching)",
        "definition": "Normalisert fatigue fra Banister (0–100).",
        "interpretation": "Høyere = mer akutt tretthet.",
        "coaching_use": "Par med fitness_score.",
        "source": "heuristic",
    },
    "recovery_score": {
        "title": "Recovery score (coaching)",
        "definition": "Sammensatt recovery fra HRV, søvn og puls.",
        "interpretation": "Høyere = bedre recovery-status.",
        "coaching_use": "Ikke Garmin readiness — intern.",
        "source": "heuristic",
    },
    "performance_score": {
        "title": "Performance score (coaching)",
        "definition": "Banister performance (fitness − fatigue) skalert 0–100.",
        "interpretation": "Høyere = bedre dagsform i modellen.",
        "coaching_use": "Dags «form» i coaching-språk.",
        "source": "heuristic",
    },
    "injury_risk_score": {
        "title": "Skaderisiko (heuristikk)",
        "definition": "Kombinasjon av ACWR, monotoni og overtraining.",
        "interpretation": "0–100, høyere = mer risiko.",
        "coaching_use": "Advar — ikke medisinsk prognose.",
        "source": "heuristic",
    },
    "overtraining_score": {
        "title": "Overtreningsscore",
        "definition": "Heuristikk fra belastning, form og HRV-flagg.",
        "interpretation": "Høyere = større risiko for overreaching.",
        "coaching_use": "Foreslå lett uke eller hvile.",
        "source": "heuristic",
    },
    "risk.overtraining_score": {
        "title": "Overtreningsrisiko (alias)",
        "definition": "Samme konsept som overtraining_score.",
        "interpretation": "Se overtraining_score.",
        "source": "heuristic",
    },
    "cardio.drift_score": {
        "title": "Cardio drift score",
        "definition": "100 minus typisk HR-drift/decoupling — høyere er bedre.",
        "interpretation": "Lav score = dårlig aerob stabilitet i perioden.",
        "coaching_use": "Aerob kvalitet over flere økter.",
        "source": "heuristic",
    },
    "predicted_5k_time": {
        "title": "Predikert 5 km-tid",
        "definition": "Estimert tid fra CS + W′-modell.",
        "interpretation": "Sekunder — lavere er raskere.",
        "coaching_use": "Målsetting — kun ved god CS-modellkvalitet.",
        "source": "heuristic",
    },
    "sleep.sleep_debt_7d": {
        "title": "Søvngjeld 7 dager",
        "definition": "Akkumulert timer under 8t søvn per natt.",
        "interpretation": "Høyere = mer uoppgjort søvn.",
        "coaching_use": "Forklar trøtthet uten hard trening.",
        "source": "computed",
    },
}
for key, entry in _GENERIC_DERIVED.items():
    METRIC_GLOSSARY.setdefault(key, entry)

# Mønstre for lagrede (auto-discovered) metrikker
STORED_PREFIX_GLOSSARY: Dict[str, Dict[str, str]] = {
    "activity.": {
        "definition": "Verdi fra én synkronisert Garmin/FIT-aktivitet.",
        "interpretation": "Se aktivitetskontekst (varighet, type, terreng).",
        "coaching_use": "Øktanalyse og sammenligning med lignende økter.",
        "source": "garmin_sync",
    },
    "health.": {
        "definition": "Daglig helsemetric (søvn, HRV, puls, body battery).",
        "interpretation": "Trend viktigere enn enkeltdag.",
        "coaching_use": "Recovery og livsstilsfaktorer.",
        "source": "garmin_sync",
    },
    "hrv.": {
        "definition": "Alias-prefix for HRV-rader i database — bruk helst health.hrv_rmssd som kanonisk nøkkel.",
        "interpretation": "Samme kilde som health.*; se metric_aliases i metric_catalog.",
        "coaching_use": "Recovery-trend; foretrekk health.hrv_rmssd i timeseries.",
        "source": "garmin_sync",
    },
    "performance.": {
        "definition": "Garmin performance status (VO2, load balance, scores).",
        "interpretation": "Offisiell Garmin-modell der merket.",
        "coaching_use": "Kapasitet og treningsstatus fra Garmin.",
        "source": "garmin_sync",
    },
}


def get_glossary_entry(metric_key: str) -> Dict[str, Any]:
    """Returner ordbokoppføring for én nøkkel, med fallback for ukjente."""
    if metric_key in METRIC_GLOSSARY:
        return {"metric_key": metric_key, **METRIC_GLOSSARY[metric_key]}

    for prefix, template in STORED_PREFIX_GLOSSARY.items():
        if metric_key.startswith(prefix):
            column = metric_key.split(".", 1)[-1]
            return {
                "metric_key": metric_key,
                "title": metric_key,
                "definition": template["definition"],
                "interpretation": f"Kolonne «{column}». {template['interpretation']}",
                "coaching_use": template["coaching_use"],
                "source": template["source"],
                "caveats": "Auto-oppdaget lagret felt — ingen manuell definisjon ennå.",
            }

    try:
        from ..services.mcp_derived_metrics_service import DERIVED_METRIC_CATALOG

        if metric_key in DERIVED_METRIC_CATALOG:
            cat = DERIVED_METRIC_CATALOG[metric_key]["category"]
            cat_help = CATEGORY_GLOSSARY.get(cat, {})
            return {
                "metric_key": metric_key,
                "title": metric_key,
                "definition": cat_help.get("definition", "Beregnet metrikk."),
                "interpretation": "Se category_glossary og metric_catalog.",
                "coaching_use": cat_help.get("coaching_use", "Tolke forsiktig."),
                "source": "derived",
                "caveats": "Mangler detaljert oppføring.",
            }
    except ImportError:
        pass

    return {
        "metric_key": metric_key,
        "title": metric_key,
        "definition": "Ingen dedikert ordboktekst — bruk metric_catalog for enhet og scope.",
        "interpretation": "Ukjent — verifiser mot datakilde før sterke coaching-påstander.",
        "coaching_use": "Hent tidsserie og tolke forsiktig.",
        "source": "unknown",
    }


def build_metric_glossary(
    *,
    metric_key: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    include_stored_patterns: bool = True,
) -> Dict[str, Any]:
    """Bygg filtrert ordbok for MCP."""
    from ..services.mcp_derived_metrics_service import DERIVED_METRIC_CATALOG
    from .training_tools import METRIC_CATALOG

    if metric_key:
        entry = get_glossary_entry(metric_key)
        definition = DERIVED_METRIC_CATALOG.get(metric_key) or METRIC_CATALOG.get(metric_key)
        if definition:
            entry["unit"] = definition.get("unit")
            entry["scope"] = definition.get("scope", "stored")
            entry["heuristic"] = definition.get("heuristic", False)
            entry["category"] = definition.get("category")
        return {"status": "ok", "entry": entry}

    entries: List[Dict[str, Any]] = []
    key_sources = set(DERIVED_METRIC_CATALOG) | set(METRIC_GLOSSARY)
    if search:
        key_sources |= set(METRIC_CATALOG)
    all_keys = sorted(key_sources)
    for key in all_keys:
        definition = DERIVED_METRIC_CATALOG.get(key) or METRIC_CATALOG.get(key) or {}
        cat = definition.get("category", "")
        if category and cat != category:
            continue
        entry = get_glossary_entry(key)
        if search:
            blob = " ".join(str(v) for v in entry.values()).lower()
            if search.lower() not in blob and search.lower() not in key.lower():
                continue
        entries.append(
            {
                **entry,
                "unit": definition.get("unit"),
                "scope": definition.get("scope", "stored" if key in METRIC_CATALOG else definition.get("scope")),
                "heuristic": definition.get("heuristic", False),
                "category": definition.get("category"),
            }
        )

    payload: Dict[str, Any] = {
        "status": "ok",
        "schema_version": "glossary-1",
        "count": len(entries),
        "disambiguation": COACHING_DISAMBIGUATION,
        "scope_descriptions": SCOPE_DESCRIPTIONS,
        "category_glossary": CATEGORY_GLOSSARY,
        "entries": entries,
    }
    if include_stored_patterns:
        payload["stored_prefix_patterns"] = STORED_PREFIX_GLOSSARY
        payload["note_stored_metrics"] = (
            f"{len(METRIC_CATALOG)} lagrede nøkler bruker prefix-mønstre når ikke eksplisitt definert. "
            "Kall med metric_key for én nøkkel, eller search= for tekstsøk."
        )
    return payload
