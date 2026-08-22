/**
 * @jest-environment jsdom
 */
import { rangeToPeriod, normalizeRange, isValidIsoDate } from "@/lib/analysisRange";
import { render, screen, fireEvent } from "@testing-library/react";
import { SinceLastUpdate } from "@/components/cockpit/SinceLastUpdate";
import { PeriodInspector } from "@/components/analysis/PeriodInspector";
import { ConnectionStatus } from "@/components/cockpit/ConnectionStatus";
import { BestPeriodBacktracePanel } from "@/components/analysis/BestPeriodBacktracePanel";

describe("analysisRange helpers", () => {
  it("maps brush spans to period chips", () => {
    expect(rangeToPeriod("2026-01-01", "2026-01-20")).toBe("28d");
    expect(rangeToPeriod("2026-01-01", "2026-03-15")).toBe("90d");
    expect(rangeToPeriod("2025-01-01", "2026-01-01")).toBe("1y");
  });

  it("normalizes inverted ranges and rejects invalid ISO", () => {
    expect(normalizeRange("2026-02-01", "2026-01-01")).toEqual({
      from: "2026-01-01",
      to: "2026-02-01",
    });
    expect(isValidIsoDate("not-a-date")).toBe(false);
    expect(normalizeRange("bad", "2026-01-01")).toBeNull();
  });
});

describe("SinceLastUpdate", () => {
  it("merges post-sync and what-changed into one compact card", () => {
    render(
      <SinceLastUpdate
        postSync={{
          activity_id: "99",
          activity_name: "Threshold 3x10",
          session_type: "threshold",
          session_quality: { label: "good", score: 92 },
          comparable: { count: 8, percentile: 25, comparison_label: "above_average" },
          plan_effect: { note: "No change" },
        }}
        whatChanged={{
          material_changes: [],
          recommendation_changed: false,
          summary: "Morning recovery updated",
        }}
      />,
    );
    expect(screen.getByText(/Since last update/i)).toBeTruthy();
    expect(screen.getByText(/Anbefaling uendret/i)).toBeTruthy();
    expect(screen.getByText(/Threshold 3x10/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Utvid/i }));
    expect(screen.getByText(/What changed/i)).toBeTruthy();
  });
});

describe("PeriodInspector", () => {
  it("renders actions for selected range", () => {
    const onViewWeeks = jest.fn();
    const onViewActivities = jest.fn();
    const onComparePrevious = jest.fn();
    render(
      <PeriodInspector
        from="2026-01-01"
        to="2026-01-28"
        onViewWeeks={onViewWeeks}
        onViewActivities={onViewActivities}
        onComparePrevious={onComparePrevious}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /VIEW WEEKS/i }));
    fireEvent.click(screen.getByRole("button", { name: /VIEW ACTIVITIES/i }));
    fireEvent.click(screen.getByRole("button", { name: /COMPARE PREVIOUS PERIOD/i }));
    expect(onViewWeeks).toHaveBeenCalled();
    expect(onViewActivities).toHaveBeenCalled();
    expect(onComparePrevious).toHaveBeenCalled();
  });
});

describe("ConnectionStatus", () => {
  it("shows offline message when backend unavailable", () => {
    render(<ConnectionStatus online={false} />);
    expect(screen.getByText(/Treningsanalyse-serveren er ikke tilgjengelig/i)).toBeTruthy();
  });

  it("shows subtle connected state", () => {
    render(<ConnectionStatus online asOf="2026-08-22" />);
    expect(screen.getByText(/Connected/i)).toBeTruthy();
  });
});

describe("BestPeriodBacktracePanel", () => {
  it("invokes onSelectRange when a preceding block is clicked", () => {
    const onSelectRange = jest.fn();
    render(
      <BestPeriodBacktracePanel
        metric="fitness.ef_30d"
        onMetricChange={jest.fn()}
        onSelectRange={onSelectRange}
        data={{
          metric: "fitness.ef_30d",
          status: "ok",
          best_periods: [
            {
              peak_date: "2026-06-01",
              peak_value: 1.2,
              preceding_blocks: [
                {
                  weeks: 4,
                  status: "ok",
                  sample_weeks: 4,
                  total_tss: 120,
                  activity_count: 8,
                  avg_weekly_duration_seconds: 18000,
                },
              ],
            },
          ],
        }}
      />,
    );
    fireEvent.click(screen.getByText(/4 uker før/i));
    expect(onSelectRange).toHaveBeenCalled();
    const [from, to] = onSelectRange.mock.calls[0];
    expect(from <= to).toBe(true);
  });
});

describe("PWA manifest", () => {
  it("is present as a static asset contract", () => {
    const fs = require("fs") as typeof import("fs");
    const path = require("path") as typeof import("path");
    const manifestPath = path.join(process.cwd(), "public", "manifest.webmanifest");
    const raw = fs.readFileSync(manifestPath, "utf8");
    const json = JSON.parse(raw);
    expect(json.display).toBe("standalone");
    expect(json.name).toMatch(/Treningsanalyse/i);
    expect(json.icons?.length).toBeGreaterThan(0);
  });

  it("ships an offline service worker shell", () => {
    const fs = require("fs") as typeof import("fs");
    const path = require("path") as typeof import("path");
    const sw = fs.readFileSync(path.join(process.cwd(), "public", "sw.js"), "utf8");
    expect(sw).toMatch(/Treningsanalyse-serveren er ikke tilgjengelig/);
  });
});

