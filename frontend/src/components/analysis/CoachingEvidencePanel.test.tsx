import { fireEvent, render, screen } from "@testing-library/react";
import { CoachingEvidencePanel, CoachingEvidenceView } from "@/components/analysis/CoachingEvidencePanel";
import type { CoachingEvidencePayload } from "@/types/coachingEvidence";

const mockUseCoachingEvidence = jest.fn();
jest.mock("@/hooks/useCoachingEvidence", () => ({
  useCoachingEvidence: (...args: unknown[]) => mockUseCoachingEvidence(...args),
}));

function payload(patch: Partial<CoachingEvidencePayload> = {}): CoachingEvidencePayload {
  return {
    status: "ok",
    read_only: true,
    period: { start: "2026-01-01", end: "2026-04-01", window_days: 90, allowed_windows: [30, 90, 180, 365] },
    maturity_legend: [
      { status: "pending", label: "Pending", text: "Outcome-vinduet er ikke ferdig ennå." },
      { status: "incomplete_data", label: "Incomplete", text: "Vinduet er ferdig, men nødvendige datapunkter manglet." },
      { status: "evaluated", label: "Evaluated", text: "Vinduet er lukket og utfallet har en verdi." },
      { status: "insufficient", label: "Insufficient evidence", text: "Enkelte outcomes finnes, men samlet N eller spredning er for lav." },
    ],
    overview: {
      canonical_recommendation_count: 2,
      mature_execution_count: 1,
      pending_count: 1,
      short_term_outcome_count: 1,
      medium_term_outcome_count: 0,
      evidence_level: "EMERGING",
      evidence_label: "Fremvoksende",
      feedback_count: 1,
      feedback_coverage: 0.5,
      explicit_match_count: 1,
      legacy_match_count: 0,
      explicit_matching_share: 1,
    },
    effectiveness: [
      {
        workout_type: "threshold",
        label: "Threshold",
        recommendation_count: 2,
        execution_count: 1,
        mature_outcome_count: 1,
        pending_count: 1,
        incomplete_count: 0,
        short_term_outcome: 0.6,
        short_term_sample_count: 1,
        medium_term_outcome: null,
        medium_term_sample_count: 0,
        session_quality: null,
        session_quality_sample_count: 0,
        observed_recovery_response: 0.4,
        observed_recovery_sample_count: 1,
        feedback_count: 1,
        evidence_level: "EMERGING",
        evidence_label: "Fremvoksende",
        conclusion_strength: "limited",
        conclusion_strength_label: "Begrenset",
        observations: [
          {
            recommendation_id: 7,
            as_of_date: "2026-03-01",
            activity_id: "99",
            execution_status: "followed",
            match_source: "explicit_execution",
            short_term_maturity: "evaluated",
            short_term_utility: 0.6,
          },
        ],
      },
    ],
    feasibility: {
      followed: 1,
      modified: 0,
      replaced: 0,
      skipped: 0,
      pending: 1,
      adherence: 0.9,
      adherence_sample_count: 1,
      evidence_label: "Utilstrekkelig",
      note: "Feasibility and adherence are not physiological effectiveness.",
    },
    confidence: {
      sample_count: 0,
      brier_score: null,
      expected_calibration_error: null,
      status: "INSUFFICIENT_DATA",
      coverage: null,
    },
    evidence_quality: {
      raw_sample_count: 1,
      effective_sample_count: 1,
      spread_days: 0,
      sufficiency_level: "INSUFFICIENT",
      sufficiency_label: "Utilstrekkelig",
      explicit_execution_matches: 1,
      legacy_heuristic_matches: 0,
      pending_windows: 1,
      incomplete_windows: 0,
    },
    signals: {
      objective: { sources: ["hrv", "rhr"], short_term_sample_count: 1, session_quality_sample_count: 0 },
      subjective: {
        sources: ["rpe", "session_feel"],
        sample_count: 1,
        coverage: 0.5,
        provenance: "athlete_feedback",
        ground_truth: false,
      },
    },
    operations: {
      abstention: { status: "INSUFFICIENT_DATA", sample_count: 2 },
      shadow: { status: "NOT_READY", note: "Eligibility ≠ promotion." },
      distribution: { unexpected_shift: false, types_from_zero: [] },
    },
    operations_lines: [
      { code: "shadow", label: "Skygge", text: "Skyggemodellen er ikke klar. Eligible er ikke en promotering." },
    ],
    what_we_know: [
      {
        workout_type: "easy_run",
        text: "Easy aerobic har 34 modne korttidsutfall. Evidens: Støttet.",
        evidence_label: "Støttet",
      },
    ],
    what_we_do_not_know: [
      { code: "insufficient_type", workout_type: "vo2_intervals", text: "VO₂-intervaller har foreløpig 6 modne observasjoner." },
    ],
    do_not_change: ["Short-term effectiveness is below SUPPORTED"],
    do_not_change_nb: ["Korttidseffekt er under støttet nivå."],
    ...patch,
  };
}

describe("CoachingEvidenceView", () => {
  it("shows learned and unknown statements, pending, and explicit matching", () => {
    render(<CoachingEvidenceView data={payload()} windowDays={90} onWindow={() => undefined} />);
    expect(screen.getByText(/Lærer coachen faktisk/)).toBeInTheDocument();
    expect(screen.getByText(/Easy aerobic har 34/)).toBeInTheDocument();
    expect(screen.getByText(/VO₂-intervaller har foreløpig 6/)).toBeInTheDocument();
    expect(screen.getByText("Outcome-vinduet er ikke ferdig ennå.")).toBeInTheDocument();
    expect(screen.getByText("Vinduet er ferdig, men nødvendige datapunkter manglet.")).toBeInTheDocument();
    expect(screen.getByText("Enkelte outcomes finnes, men samlet N eller spredning er for lav.")).toBeInTheDocument();
    expect(screen.getByText("100 %")).toBeInTheDocument();
    expect(screen.getByText(/Eksplisitt 1/)).toBeInTheDocument();
    expect(screen.getByText(/INSUFFICIENT_DATA/)).toBeInTheDocument();
    expect(screen.getByText(/Restitusjon 0.40/)).toBeInTheDocument();
    expect(screen.getByText(/Konklusjonsstyrke Begrenset/)).toBeInTheDocument();
    expect(screen.getByText(/Eligible er ikke en promotering/)).toBeInTheDocument();
    expect(screen.getByText(/Korttidseffekt er under støttet nivå/)).toBeInTheDocument();
    expect(screen.queryByText(/Short-term effectiveness is below SUPPORTED/)).not.toBeInTheDocument();
  });

  it("shows an empty state without a learned conclusion", () => {
    const data = payload();
    data.overview.canonical_recommendation_count = 0;
    data.what_we_know = [];
    data.effectiveness = [];
    render(<CoachingEvidenceView data={data} windowDays={90} onWindow={() => undefined} />);
    expect(screen.getByText("Ingen kanoniske anbefalinger i vinduet")).toBeInTheDocument();
    expect(screen.getByText("Ingen støttet eller fremvoksende læring i vinduet")).toBeInTheDocument();
  });

  it("opens the observation drill-down", () => {
    render(<CoachingEvidenceView data={payload()} windowDays={90} onWindow={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Vis observasjoner" }));
    expect(screen.getByRole("link", { name: "Åpne økt" })).toHaveAttribute("href", "/activities/99");
    expect(screen.getByText(/eksplisitt/)).toBeInTheDocument();
  });

  it("renders loading and error from the query", () => {
    mockUseCoachingEvidence.mockReturnValue({ isLoading: true, isError: false, data: undefined });
    const { rerender } = render(<CoachingEvidencePanel />);
    expect(screen.getByRole("status", { name: "Laster coaching-evidens" })).toBeInTheDocument();
    mockUseCoachingEvidence.mockReturnValue({
      isLoading: false,
      isError: true,
      error: new Error("offline"),
      data: undefined,
      refetch: jest.fn(),
    });
    rerender(<CoachingEvidencePanel />);
    expect(screen.getByRole("alert")).toHaveTextContent("Kunne ikke laste coaching-evidens");
    expect(screen.getByText("offline")).toBeInTheDocument();
  });

  it("changes the analysis window without inventing a score", () => {
    const onWindow = jest.fn();
    render(<CoachingEvidenceView data={payload()} windowDays={90} onWindow={onWindow} />);
    fireEvent.click(screen.getByRole("button", { name: "30 dager" }));
    expect(onWindow).toHaveBeenCalledWith(30);
    expect(screen.queryByText(/CoachScore/)).not.toBeInTheDocument();
  });
});
