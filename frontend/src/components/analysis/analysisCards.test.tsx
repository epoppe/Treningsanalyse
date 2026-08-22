/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import { TrendSummaryCard } from "@/components/analysis/TrendSummaryCard";
import { RelationshipCard } from "@/components/analysis/RelationshipCard";

describe("TrendSummaryCard", () => {
  it("shows direction and evidence without fake precision spam", () => {
    render(
      <TrendSummaryCard
        domain={{
          domain: "aerobic_efficiency",
          metric: "easy_run_efficiency",
          label: "Aerob effektivitet",
          direction: "improving",
          direction_label: "Forbedring",
          relative_change_pct: 4.2,
          current: 1.23456,
          sample_count: 18,
          evidence: "supported",
        }}
      />
    );
    expect(screen.getByText("Aerob effektivitet")).toBeTruthy();
    expect(screen.getByText(/\+4\.1%|\+4\.2%/)).toBeTruthy();
    expect(screen.getByText(/Støttet/i)).toBeTruthy();
    expect(screen.getByText(/n=18/)).toBeTruthy();
  });
});

describe("RelationshipCard", () => {
  it("uses observational wording and never claims cause", () => {
    render(
      <RelationshipCard
        card={{
          id: "easy_volume_efficiency",
          question: "Henger lett volum sammen med aerob effektivitet?",
          stimulus: "easy_volume",
          outcome: "easy_efficiency",
          section: "TRAINING → FITNESS",
          status: "ok",
          association: "positive",
          strength: "moderate",
          lag_days: 21,
          sample_count: 16,
          evidence: "supported",
          wording:
            "easy volume er historisk knyttet til easy efficiency (observasjonell assosiasjon — ikke årsak).",
        }}
      />
    );
    expect(screen.getByText(/ikke årsak/i)).toBeTruthy();
    expect(screen.queryByText(/årsaker/i)).toBeNull();
    expect(screen.getByText(/lag 21d/)).toBeTruthy();
  });
});
