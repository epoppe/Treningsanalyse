import { fireEvent, render, screen } from "@testing-library/react";
import { RecommendationHistoryPanel } from "@/components/cockpit/RecommendationHistoryPanel";

const mockUseRecommendationHistory = jest.fn();

jest.mock("@/hooks/useDashboard", () => ({
  useRecommendationHistory: (...args: unknown[]) => mockUseRecommendationHistory(...args),
}));

jest.mock("next/link", () => {
  return ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  );
});

describe("RecommendationHistoryPanel", () => {
  beforeEach(() => {
    mockUseRecommendationHistory.mockReturnValue({
      data: {
        items: [
          {
            id: 1,
            as_of_date: "2026-08-22",
            recommended: "threshold",
            actual_type: "threshold",
            activity_id: "99",
            execution_status: "followed",
            execution_quality: 0.9,
          },
        ],
        count: 1,
        disclaimer: "Observational only",
      },
      isLoading: false,
    });
  });

  it("renders richer columns and filters", () => {
    render(<RecommendationHistoryPanel />);
    expect(screen.getByText("Anbefalingshistorikk")).toBeInTheDocument();
    expect(screen.getByText("Anbefalt")).toBeInTheDocument();
    expect(screen.getByText("Faktisk")).toBeInTheDocument();
    expect(screen.getByText("Gjennomføring")).toBeInTheDocument();
    expect(screen.getByText("Fulgt")).toBeInTheDocument();
    expect(screen.getByText("90%")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Justert" }));
    expect(mockUseRecommendationHistory).toHaveBeenCalledWith(40, "modified");
  });
});
