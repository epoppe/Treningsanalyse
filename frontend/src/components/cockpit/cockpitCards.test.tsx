import { render, screen } from "@testing-library/react";
import { NextWorkoutCard } from "@/components/cockpit/NextWorkoutCard";
import { WhyThisWorkout } from "@/components/cockpit/WhyThisWorkout";
import { WhatChangedCard } from "@/components/cockpit/WhatChangedCard";
import { PlanChangeTimeline } from "@/components/cockpit/PlanChangeTimeline";
import { PlanVsActualTable } from "@/components/cockpit/PlanVsActualTable";
import { MesocycleOverview } from "@/components/cockpit/MesocycleOverview";
import type { TodayDashboardPayload } from "@/types/today";

const thresholdPayload: TodayDashboardPayload = {
  as_of: "2026-08-22",
  recommendation: {
    decision_status: "recommend",
    workout_type: "threshold",
    prescription: {
      title: "3 x 10 min controlled threshold",
      total_duration_min: 58,
      main_set: {
        repetitions: 3,
        work_duration_min: 10,
        recovery_duration_min: 2,
        target_hr: [158, 164],
        target_pace: [335, 345],
        target_rpe: [7, 8],
      },
    },
    confidence: 0.74,
    evidence_strength: 0.68,
  },
  decision_explanation: {
    top_reasons: [
      { code: "QUALITY_SESSION_DUE", doc: "Spacing supports quality" },
      { code: "RECOVERY_LOW", doc: "Recovery supports training" },
    ],
    evidence_strength: 0.68,
    decision_confidence: 0.74,
  },
};

const abstainPayload: TodayDashboardPayload = {
  recommendation: {
    decision_status: "abstain",
    safe_alternatives: [
      { workout_type: "easy_run", rationale: "Trygg volumøkt" },
      { workout_type: "recovery_run", rationale: "Ekstra restitusjon" },
    ],
  },
};

describe("NextWorkoutCard", () => {
  it("renders a normal threshold recommendation", () => {
    render(<NextWorkoutCard data={thresholdPayload} />);
    expect(screen.getByText(/3 x 10 min controlled threshold/i)).toBeInTheDocument();
    expect(screen.getByText(/158–164 slag\/min/i)).toBeInTheDocument();
    expect(screen.getByText(/5:35\/km–5:45\/km/i)).toBeInTheDocument();
  });

  it("renders abstain alternatives instead of a single prescription", () => {
    render(<NextWorkoutCard data={abstainPayload} />);
    expect(screen.getByText(/To trygge alternativer/i)).toBeInTheDocument();
    expect(screen.getByText(/Alternativ A/i)).toBeInTheDocument();
    expect(screen.getByText(/Rolig løp/i)).toBeInTheDocument();
  });
});

describe("WhatChangedCard", () => {
  it("renders recommendation change summary", () => {
    render(
      <WhatChangedCard
        data={{
          material_changes: [
            {
              metric: "hrv_delta_pct",
              label: "HRV",
              before: 2,
              after: 6,
              direction: "improved",
            },
          ],
          recommendation_changed: true,
          before_recommendation: "easy_run",
          after_recommendation: "threshold",
          summary: "Anbefaling endret.",
        }}
      />,
    );
    expect(screen.getByText(/Hva endret seg/i)).toBeInTheDocument();
    expect(screen.getByText(/Rolig løp → Kontrollert terskel/i)).toBeInTheDocument();
  });
});

describe("WhyThisWorkout", () => {
  it("shows top reasons at level 1", () => {
    render(
      <WhyThisWorkout
        explanation={thresholdPayload.decision_explanation}
        workoutType="threshold"
      />,
    );
    expect(screen.getByText(/Kvalitetsøkt er due etter god spacing/i)).toBeInTheDocument();
  });
});

describe("Plan cockpit components", () => {
  it("renders plan change timeline with Norwegian reason", () => {
    render(
      <PlanChangeTimeline
        history={[
          {
            version: 2,
            created_at: "2026-08-20T10:00:00+00:00",
            reason: ["no_quality_conflict"],
            week_objective: "Bygg terskel",
          },
        ]}
      />,
    );
    expect(screen.getByText(/Bygg terskel/i)).toBeInTheDocument();
    expect(screen.getByText(/Ingen planendring nødvendig/i)).toBeInTheDocument();
  });

  it("renders plan vs actual table", () => {
    render(
      <PlanVsActualTable
        days={[
          {
            date: "2026-08-18",
            weekday: 0,
            planned_type: "threshold",
            actual_type: "threshold",
            execution_status: "followed",
          },
        ]}
      />,
    );
    expect(screen.getAllByText(/Kontrollert terskel/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Fulgt/i)).toBeInTheDocument();
  });

  it("renders mesocycle overview", () => {
    render(
      <MesocycleOverview
        weeks={[
          {
            week: 1,
            phase: "build",
            target_volume: [220, 320],
            quality_sessions: 2,
            primary_stimulus: "threshold",
          },
        ]}
      />,
    );
    expect(screen.getByText(/Uke 1/i)).toBeInTheDocument();
    expect(screen.getByText(/Oppbygging/i)).toBeInTheDocument();
  });
});
