import { render, screen } from "@testing-library/react";
import { NextWorkoutCard } from "@/components/cockpit/NextWorkoutCard";
import { WhyThisWorkout } from "@/components/cockpit/WhyThisWorkout";
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
