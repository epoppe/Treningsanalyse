/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { WhyThisWorkout } from "@/components/coaching/WhyThisWorkout";
import { NextWorkoutCard } from "@/components/coaching/NextWorkoutCard";
import { WeeklyTrainingPlan } from "@/components/coaching/WeeklyTrainingPlan";

describe("WhyThisWorkout", () => {
  it("shows Norwegian reason chips from backend codes", () => {
    render(
      <WhyThisWorkout
        explanation={{
          reason_codes: ["QUALITY_SESSION_DUE", "DATA_STALE"],
          evidence_strength: 0.7,
          decision_confidence: 0.6,
        }}
      />
    );
    expect(screen.getByText(/Tid for kvalitetsøkt/i)).toBeTruthy();
    expect(screen.getByText(/gamle/i)).toBeTruthy();
  });

  it("progressive disclosure expands evidence", () => {
    render(
      <WhyThisWorkout
        explanation={{
          reason_codes: ["DEFAULT_AEROBIC"],
          evidence_strength: 0.81,
          decision_confidence: 0.55,
        }}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /Vis mer/i }));
    expect(screen.getByTestId("why-details")).toBeTruthy();
    expect(screen.getByText(/0\.81/)).toBeTruthy();
  });
});

describe("WeeklyTrainingPlan", () => {
  it("formats duration ranges without concatenating numbers", () => {
    render(
      <WeeklyTrainingPlan
        plan={{
          week_objective: "test",
          sessions: [{ day_offset: 0, type: "easy_run", duration_min: [45, 60] }],
        }}
      />
    );
    expect(screen.getByText("45–60m")).toBeTruthy();
    expect(screen.queryByText(/4560/)).toBeNull();
  });
});

describe("NextWorkoutCard", () => {
  it("renders threshold hero and uncertainty when pace missing", () => {
    render(
      <NextWorkoutCard
        recommendation={{
          workout_type: "threshold",
          duration_min: 58,
          target_hr: [158, 164],
          decision_status: "recommend",
          decision_confidence: 0.8,
          evidence_strength: 0.7,
        }}
        prescription={{
          total_duration_min: 58,
          main_set: { repetitions: 3, work_duration_min: 10 },
        }}
      />
    );
    expect(screen.getByText("Terskel")).toBeTruthy();
    expect(screen.getByText(/3 × 10 min/)).toBeTruthy();
    expect(screen.getAllByText(/HR\/RPE/i).length).toBeGreaterThan(0);
  });

  it("renders rest without intensity targets", () => {
    render(
      <NextWorkoutCard recommendation={{ workout_type: "rest", decision_status: "recommend" }} />
    );
    expect(screen.getByText("Hvile")).toBeTruthy();
  });
});
