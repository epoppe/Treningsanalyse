"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Cockpit-aligned page chrome for metric drill-downs. */
export function MetricPageLayout({
  eyebrow = "Drill-down",
  title,
  subtitle,
  children,
  className,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-4", className)}>
      <header className="space-y-1">
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
          {eyebrow}
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {subtitle ? <p className="text-sm text-slate-600">{subtitle}</p> : null}
      </header>
      {children}
    </div>
  );
}

export function MetricFilterCard({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function MetricPeriodChip({
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

export function MetricDateField({
  id,
  label,
  value,
  onChange,
  min,
  max,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  min?: string;
  max?: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm text-slate-700" htmlFor={id}>
      <span className="font-medium">{label}</span>
      <input
        id={id}
        type="date"
        value={value}
        min={min}
        max={max}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900"
      />
    </label>
  );
}

export function MetricPrimaryButton({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900",
        disabled ? "cursor-not-allowed opacity-50" : "hover:bg-slate-800",
      )}
    >
      {children}
    </button>
  );
}

export function MetricStatGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">{children}</div>
  );
}

export function MetricStatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: ReactNode;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
        {label}
      </p>
      <p
        className="mt-1 text-xl font-semibold tabular-nums text-slate-900"
        style={accent ? { color: accent } : undefined}
      >
        {value}
      </p>
    </div>
  );
}

export function MetricAlert({
  children,
  tone = "error",
}: {
  children: ReactNode;
  tone?: "error" | "info" | "empty";
}) {
  const styles =
    tone === "error"
      ? "border-red-200 bg-red-50 text-red-700"
      : tone === "info"
        ? "border-slate-200 bg-slate-50 text-slate-600"
        : "border-slate-200 bg-white text-slate-600";
  return (
    <div className={cn("rounded-xl border px-4 py-3 text-sm shadow-sm", styles)} role="status">
      {children}
    </div>
  );
}

export function MetricLoading({ children = "Laster data..." }: { children?: ReactNode }) {
  return (
    <div className="flex h-40 items-center justify-center rounded-xl border border-slate-200 bg-white text-sm text-slate-500 shadow-sm">
      {children}
    </div>
  );
}
