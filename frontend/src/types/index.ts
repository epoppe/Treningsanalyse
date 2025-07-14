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
  totalTrainingEffect?: number;
  totalAnaerobicTrainingEffect?: number;
  details?: { [key: string]: any };
} 