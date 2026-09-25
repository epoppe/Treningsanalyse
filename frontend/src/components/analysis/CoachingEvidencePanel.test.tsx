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
      bins: [{ bin: "0.5-0.6", n: 4, predicted_mean: 0.55, empirical_frequency: 0.5 }],
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
        fields: { rpe: 1, session_feel: 1, legs: 0, motivation: 0, pain: 0 },
        quality_session_count: 2,
        quality_feedback_count: 1,
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
    coaching_change: {
      status: "INSUFFICIENT_EVIDENCE",
      text: "For lite prospektiv evidens til å konkludere om coachen har blitt bedre.",
    },
    data_quality_snapshot: {
      schema: "data-quality-snapshot-1",
      freshness: { last_sync_at: null, last_activity_at: null, stale_local_despite_source: false },
      missing_sources: [{ source: "hrv", reason: "no rows" }],
      coverage_shifts: [],
      observations: { pending: 1, evaluated: 1, incomplete: 0, excluded: 2 },
      feedback_coverage: 0.5,
      feedback_by_group: {
        easy: { recommendations: 2, with_feedback: 1, coverage: 0.5 },
        long: { recommendations: 0, with_feedback: 0, coverage: null },
        threshold: { recommendations: 0, with_feedback: 0, coverage: null },
        intervals: { recommendations: 0, with_feedback: 0, coverage: null },
        race: { recommendations: 0, with_feedback: 0, coverage: null },
      },
    },
    ...patch,
  };
}

describe("CoachingEvidenceView", () => {
  it("shows learned and unknown statements, pending, and explicit matching", () => {
    render(<CoachingEvidenceView data={payload()} windowDays={90} onWindow={() => undefined} />);
    expect(screen.getByText(/Lærer coachen faktisk/)).toBeInTheDocument();
    expect(screen.getByText(/For lite prospektiv evidens til å konkludere/)).toBeInTheDocument();
    expect(screen.getByText(/Siste sync ukjent/)).toBeInTheDocument();
    expect(screen.getByText(/utelatt 2/)).toBeInTheDocument();
    expect(screen.getByText(/Manglende kilder: hrv/)).toBeInTheDocument();
    expect(screen.getByText(/Feedback rolig 50 %/)).toBeInTheDocument();
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
    expect(screen.getByText(/RPE 1/)).toBeInTheDocument();
    expect(screen.getByText(/Kvalitetsøkter 1 av 2/)).toBeInTheDocument();
    expect(screen.queryByText(/0.5-0.6/)).not.toBeInTheDocument();
  });

  it("shows an observational before/after only when the payload includes one", () => {
    const data = payload({
      coaching_change: {
        status: "OBSERVATIONAL",
        text: "Korttidsutfall er høyere i andre halvdel (0.70) enn i første (0.40), N 12 og 12. Observasjonelt, ikke en påvist effekt av coachen.",
      },
    });
    render(<CoachingEvidenceView data={data} windowDays={90} onWindow={() => undefined} />);
    expect(screen.getByText(/ikke en påvist effekt av coachen/)).toBeInTheDocument();
    expect(screen.queryByText(/For lite prospektiv evidens til å konkludere/)).not.toBeInTheDocument();
  });

  it("shows calibration bins only when the status is not insufficient", () => {
    const data = payload();
    data.confidence.status = "well_calibrated";
    data.overview.evidence_level = "SUPPORTED";
    data.overview.evidence_label = "Støttet";
    render(<CoachingEvidenceView data={data} windowDays={90} onWindow={() => undefined} />);
    expect(screen.getByText("Støttet")).toBeInTheDocument();
    expect(screen.getByText(/0.5-0.6/)).toBeInTheDocument();
    expect(screen.getByText(/predikert 0.55/)).toBeInTheDocument();
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
