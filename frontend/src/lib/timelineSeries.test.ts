import { groupSeriesByUnit, insertGapNulls, seriesShowsGaps, sharesRawAxis } from "./timelineSeries";

describe("timeline unit panels", () => {
  it("never puts incompatible units on one raw axis", () => {
    const groups = groupSeriesByUnit(["fitness.ctl", "cardio.hrv_7d", "running.critical_speed"], {
      "fitness.ctl": { unit: "load" },
      "cardio.hrv_7d": { unit: "ms" },
      "running.critical_speed": { unit: "km/h" },
    });
    expect(groups).toHaveLength(3);
    expect(sharesRawAxis(groups)).toBe(false);
    expect(groups.every((group) => new Set(group.map((key) => key)).size === group.length)).toBe(true);
  });

  it("keeps the same unit together", () => {
    const groups = groupSeriesByUnit(["running.speed_5m_hist", "running.critical_speed"], {
      "running.speed_5m_hist": { unit: "km/h" },
      "running.critical_speed": { unit: "km/h" },
    });
    expect(sharesRawAxis(groups)).toBe(true);
  });

  it("shows holes in a daily series and not in a snapshot", () => {
    expect(seriesShowsGaps({ temporal_semantics: "rolling_mean", native_cadence_days: 1, show_gaps: true })).toBe(
      true,
    );
    expect(seriesShowsGaps({ temporal_semantics: "snapshot", show_gaps: false })).toBe(false);
    const rows = insertGapNulls(
      [
        { date: "2026-09-01", value: 40 },
        { date: "2026-09-03", value: 42 },
      ],
      true,
    );
    expect(rows.map((row) => row.value)).toEqual([40, null, 42]);
  });
});
