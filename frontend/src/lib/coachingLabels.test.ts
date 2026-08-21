import { reasonLabel, workoutLabel, oneSentenceSummary, formatPace } from "./coachingLabels";

describe("coachingLabels", () => {
  it("maps reason codes to Norwegian labels", () => {
    expect(reasonLabel("QUALITY_SESSION_DUE")).toMatch(/kvalitets/i);
    expect(reasonLabel("RECOVERY_LOW")).toMatch(/Restitusjon/i);
    expect(reasonLabel("DATA_STALE")).toMatch(/gamle/i);
  });

  it("maps workout types", () => {
    expect(workoutLabel("threshold")).toBe("Terskel");
    expect(workoutLabel("rest")).toBe("Hvile");
  });

  it("builds one-sentence summary for rest and abstain", () => {
    expect(oneSentenceSummary({ workoutType: "rest", decisionStatus: "recommend" })).toMatch(
      /Restitusjon/i
    );
    expect(
      oneSentenceSummary({ workoutType: "easy_run", decisionStatus: "abstain" })
    ).toMatch(/For lite/i);
  });

  it("formats pace", () => {
    expect(formatPace(330)).toBe("5:30/km");
    expect(formatPace(null)).toBe("—");
  });
});
