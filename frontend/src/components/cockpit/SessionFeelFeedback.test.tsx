import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { coachingEvidenceApi } from "@/dashboard/coachingEvidenceApi";
import { SessionFeelFeedback } from "@/components/cockpit/SessionFeelFeedback";

jest.mock("@/dashboard/coachingEvidenceApi", () => ({
  coachingEvidenceApi: {
    feedback: jest.fn(),
    prompt: jest.fn(),
    saveFeedback: jest.fn(),
  },
}));

const api = coachingEvidenceApi as unknown as {
  feedback: jest.Mock;
  prompt: jest.Mock;
  saveFeedback: jest.Mock;
};

const feedbackBody = {
  status: "ok",
  activity_id: "42",
  feedback: null,
  quick_feel: [
    { value: "easy", label: "Lettere enn forventet" },
    { value: "as_expected", label: "Som forventet" },
    { value: "hard", label: "Tyngre enn forventet" },
  ],
  rpe: { min: 1, max: 10 },
  pain: { min: 0, max: 10 },
  motivation: { min: 1, max: 5 },
  legs: ["fresh", "normal", "heavy"],
};

describe("SessionFeelFeedback", () => {
  beforeEach(() => {
    api.feedback.mockReset();
    api.prompt.mockReset();
    api.saveFeedback.mockReset();
  });

  it("saves a quick feel and keeps it selected", async () => {
    api.feedback.mockResolvedValue(feedbackBody);
    api.prompt.mockResolvedValue({
      status: "ok",
      activity_id: "42",
      should_prompt: true,
      priority: "useful",
      reasons: ["race"],
      reason_labels: ["Konkurranse gir mer informasjon enn en vanlig rolig økt."],
      already_has_feedback: false,
    });
    api.saveFeedback.mockResolvedValue({
      ...feedbackBody,
      feedback: {
        id: 1,
        activity_id: "42",
        session_feel: "easy",
        rpe: null,
        legs: null,
        pain: null,
        motivation: null,
        notes: null,
      },
    });

    render(<SessionFeelFeedback activityId="42" />);
    expect(await screen.findByText(/høy informasjonsverdi/)).toBeInTheDocument();
    expect(screen.getByText(/Konkurranse gir mer informasjon/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Lettere enn forventet" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Lettere enn forventet" })).toHaveAttribute(
        "aria-pressed",
        "true",
      ),
    );
    expect(screen.queryByText(/høy informasjonsverdi/)).not.toBeInTheDocument();
    expect(api.saveFeedback).toHaveBeenCalledWith("42", expect.objectContaining({ session_feel: "easy" }));
  });

  it("does not prompt when feedback already exists and shows the saved value", async () => {
    api.feedback.mockResolvedValue({
      ...feedbackBody,
      feedback: {
        id: 3,
        activity_id: "42",
        session_feel: "hard",
        rpe: 8,
        legs: "heavy",
        pain: 1,
        motivation: 2,
        notes: null,
      },
    });
    api.prompt.mockResolvedValue({
      status: "ok",
      should_prompt: false,
      already_has_feedback: true,
      priority: "none",
      reasons: ["already_has_feedback"],
      activity_id: "42",
    });
    render(<SessionFeelFeedback activityId="42" />);
    expect(await screen.findByRole("button", { name: "Tyngre enn forventet" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.queryByText(/høy informasjonsverdi/)).not.toBeInTheDocument();
  });

  it("expands optional fields and shows a save error", async () => {
    api.feedback.mockResolvedValue(feedbackBody);
    api.prompt.mockResolvedValue({
      status: "ok",
      should_prompt: false,
      already_has_feedback: false,
      priority: "none",
      reasons: [],
      activity_id: "42",
    });
    api.saveFeedback.mockRejectedValue(new Error("invalid"));
    render(<SessionFeelFeedback activityId="42" />);
    fireEvent.click(await screen.findByRole("button", { name: "Mer" }));
    expect(screen.getByText(/RPE \(1–10\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Som forventet" }));
    expect(await screen.findByText("invalid")).toBeInTheDocument();
  });
});
