/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { WhyThisWorkout } from "@/components/coaching/WhyThisWorkout";
import { NextWorkoutCard } from "@/components/coaching/NextWorkoutCard";

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
    expect(screen.getByText(/0\.81/)).toBeTruthy();
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
    expect(screen.getByText(/Bruk puls\/RPE/i)).toBeTruthy();
  });

  it("renders rest without intensity targets", () => {
    render(
      <NextWorkoutCard recommendation={{ workout_type: "rest", decision_status: "recommend" }} />
    );
    expect(screen.getByText("Hvile")).toBeTruthy();
  });
});
