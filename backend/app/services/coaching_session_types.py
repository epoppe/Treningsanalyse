"""Delte session-/workout-typekonstanter for coaching-tjenester.

Holdes utenfor NextBestWorkoutService for å unngå sirkulære importer
mellom load-variability, kalibrering og anbefaling.
"""

from __future__ import annotations

HARD_SESSION_TYPES = frozenset({"threshold", "vo2_intervals", "tempo", "anaerobic", "race"})
HARD_WORKOUT_TYPES = frozenset({"threshold", "vo2_intervals", "race_pace"})
EASY_SESSION_TYPES = frozenset({"easy_run", "recovery", "long_run"})
