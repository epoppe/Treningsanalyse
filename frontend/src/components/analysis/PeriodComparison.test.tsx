/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import { PeriodComparison } from "./PeriodComparison";

describe("PeriodComparison", () => {
  it("labels the exact window and shows the metric unit", () => {
    render(
      <PeriodComparison
        days={45}
        exactRange
        rows={[
          {
            metric: "critical_speed",
            unit: "km/h",
            period_a: { label: "a", end: "2026-02-14", value: 14.4, sample_count: 5 },
            period_b: { label: "b", end: "2025-12-31", value: 14.0, sample_count: 5 },
            difference: 0.4,
            evidence: "uncertain",
          },
        ]}
      />,
    );
    expect(screen.getByText(/Siste 45 dager vs forrige 45 dager/)).toBeTruthy();
    expect(screen.getByText("(km/h)")).toBeTruthy();
    expect(screen.getByText("14.4")).toBeTruthy();
  });
});
