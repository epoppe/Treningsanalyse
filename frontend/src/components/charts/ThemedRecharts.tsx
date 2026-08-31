"use client";

import type { ComponentProps } from "react";
import {
  CartesianGrid,
  Legend,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  CHART_AXIS,
  CHART_GRID,
  CHART_LEGEND,
  CHART_MARGIN,
  CHART_TOOLTIP,
} from "./chartTheme";

export { CHART_MARGIN, chartColor, yearComparisonColors } from "./chartTheme";

/**
 * Recharts 2.x registers X/Y axes from children by displayName + defaultProps.
 * Function wrappers that return <XAxis/> break axis context — subclass instead.
 */
export const ThemedXAxis = class ThemedXAxis extends XAxis {
  static displayName = "XAxis";
  static defaultProps = {
    ...XAxis.defaultProps,
    tick: CHART_AXIS.tick,
    axisLine: { stroke: CHART_AXIS.stroke },
    tickLine: { stroke: CHART_AXIS.stroke },
    minTickGap: 24,
  };
} as typeof XAxis;

export const ThemedYAxis = class ThemedYAxis extends YAxis {
  static displayName = "YAxis";
  static defaultProps = {
    ...YAxis.defaultProps,
    width: 48,
    tick: CHART_AXIS.tick,
    axisLine: { stroke: CHART_AXIS.stroke },
    tickLine: { stroke: CHART_AXIS.stroke },
  };
} as typeof YAxis;

/**
 * CartesianGrid is a rendering function component — plain wrapper without
 * spoofing displayName so it renders as a normal chart child.
 */
export function ThemedCartesianGrid(props: ComponentProps<typeof CartesianGrid>) {
  return <CartesianGrid {...CHART_GRID} {...props} />;
}

export function ThemedTooltip(props: ComponentProps<typeof Tooltip>) {
  return (
    <Tooltip
      contentStyle={CHART_TOOLTIP.contentStyle}
      labelStyle={CHART_TOOLTIP.labelStyle}
      itemStyle={CHART_TOOLTIP.itemStyle}
      {...props}
    />
  );
}

export function ThemedLegend(props: Omit<ComponentProps<typeof Legend>, "ref">) {
  return <Legend wrapperStyle={CHART_LEGEND.wrapperStyle} {...props} />;
}

/** Spreadable props for gradual legacy migration */
export const themedGridProps = CHART_GRID;
export const themedAxisTick = CHART_AXIS.tick;
export const themedTooltipContentStyle = CHART_TOOLTIP.contentStyle;
export const themedLegendWrapperStyle = CHART_LEGEND.wrapperStyle;
