"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function ChartShell({
  title,
  subtitle,
  children,
  emptyMessage = "Ingen data å vise for denne perioden.",
  isEmpty = false,
  className,
  heightClassName = "h-64",
}: {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  emptyMessage?: string;
  isEmpty?: boolean;
  className?: string;
  heightClassName?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-xl border border-slate-200 bg-white shadow-sm",
        className,
      )}
    >
      {title ? (
        <header className="border-b border-slate-100 px-4 py-3">
          <h3 className="text-base font-semibold text-slate-900">{title}</h3>
          {subtitle ? <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p> : null}
        </header>
      ) : null}
      <div className={cn("px-4 py-3", heightClassName)}>
        {isEmpty ? (
          <p className="flex h-full items-center justify-center text-sm text-slate-500">
            {emptyMessage}
          </p>
        ) : (
          children
        )}
      </div>
    </section>
  );
}

/** Styled-components replacement for legacy metric charts */
export function LegacyChartFrame({
  title,
  children,
  controls,
  className,
  height = "600px",
}: {
  title: string;
  children: ReactNode;
  controls?: ReactNode;
  className?: string;
  height?: string;
}) {
  return (
    <div
      className={cn(
        "mb-4 rounded-lg border border-slate-200 bg-white p-3 shadow-sm",
        className,
      )}
      style={{ minHeight: height }}
    >
      <h3 className="mb-2 text-base font-semibold text-slate-900">{title}</h3>
      {controls ? <div className="mb-3 flex flex-wrap gap-2">{controls}</div> : null}
      {children}
    </div>
  );
}

export function LegacyChartToggle({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-md border px-3 py-1.5 text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900",
        active
          ? "border-slate-900 bg-slate-900 text-white"
          : "border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100",
      )}
    >
      {children}
    </button>
  );
}

export function LegacyInfoPanel({ children }: { children: ReactNode }) {
  return (
    <div className="mb-3 rounded-md border border-slate-100 bg-slate-50 px-3 py-2 text-sm text-slate-600">
      {children}
    </div>
  );
}
