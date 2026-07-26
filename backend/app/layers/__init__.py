"""Tre datalag for Treningsanalyse.

Lag 1 – Raw: Garmin API / FIT-bytes / detailed_metrics (kun ingest & raw_access)
Lag 2 – Normalisert: Activity ORM + parquet FitSeries
Lag 3 – Avledet: metrics/analysis/PPAP (kun Activity + FitSeries)

Regel: Beregningskode (lag 3) skal ikke lese Garmin JSON direkte.
"""

from .normalized import NormalizedActivity, load_fit_series, to_normalized_activity
from .raw_access import materialize_fit_series_from_raw

__all__ = [
    "NormalizedActivity",
    "load_fit_series",
    "to_normalized_activity",
    "materialize_fit_series_from_raw",
]
