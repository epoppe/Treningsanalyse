// Definerer delte typer for hele applikasjonen for å unngå sirkulære avhengigheter.

export interface Activity {
  activityId: string;
  activityName?: string;
  activityType?: {
    typeKey?: string;
    parentTypeKey?: string;
  };
  averageHR?: number;
  averagePace?: number;
  averageRunningCadenceInStepsPerMinute?: number;
  averageSpeed?: number;
  avgStrideLength?: number;
  calories?: number;
  distance?: number;
  duration?: number;
  startTimeLocal: string;
  vO2MaxValue?: number;
  negativeSplitPercent?: number;
  decouplingPercent?: number;
  trainingReadinessScore?: number;
  totalTrainingEffect?: number;
  totalAnaerobicTrainingEffect?: number;
  epoc?: number;  // Exercise Post Oxygen Consumption (Training Load) - også brukt som TSS
  averagePowerWatts?: number;  // Gjennomsnittlig power i watt
  lactateThresholdSpeed?: number;  // Lactate threshold speed in m/s
  details?: { [key: string]: any };
} 