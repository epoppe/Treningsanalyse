export const getReadinessStatusText = (status: string): string => {
  const statusMap: Record<string, string> = {
    optimal: 'Optimal',
    good: 'God',
    moderate: 'Moderat',
    poor: 'Dårlig',
    very_poor: 'Svært dårlig',
    unknown: 'Ukjent',
  };
  return statusMap[status] || status;
};

export const getReadinessRecommendation = (
  status: string,
  hasTrainedOnDate?: boolean,
): string => {
  const baseRecommendations: Record<string, string> = {
    optimal: 'Du er klar for intensiv trening. Gå for det!',
    good: 'Du kan gjøre moderat til intensiv trening. Lytt til kroppen.',
    moderate: 'Gjør lett til moderat trening. Fokuser på teknikk og form.',
    poor: 'Gjør lett trening eller hvile. Prioriter recovery.',
    very_poor: 'Ta en hviledag. Fokuser på søvn og recovery.',
    unknown: 'Ikke nok data til å gi anbefaling.',
  };

  const base = baseRecommendations[status] || 'Ingen anbefaling tilgjengelig.';
  if (hasTrainedOnDate === undefined) {
    return base;
  }

  return hasTrainedOnDate
    ? `Du har trent denne dagen. ${base}`
    : `Du har ikke trent denne dagen. ${base}`;
};

export const getReadinessScoreColor = (score: number): string => {
  if (score >= 80) return '#10b981';
  if (score >= 60) return '#3b82f6';
  if (score >= 40) return '#f59e0b';
  if (score >= 20) return '#ef4444';
  return '#6b7280';
};

export const getFormValueDescription = (formValue: number): string => {
  if (formValue < -15) return '🔴 Høy fysisk fatigue';
  if (formValue < -5) return '🟡 Moderat fysisk fatigue';
  if (formValue < 5) return '🟢 Balansert';
  if (formValue < 15) return '🟢 Godt restituert';
  return '🟢 Meget frisk';
};
