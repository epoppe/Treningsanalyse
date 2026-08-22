"use client";

import { Suspense } from "react";
import AnalyseWorkspace from "./AnalyseWorkspace";
import { AnalysisSkeleton } from "@/components/analysis/ui";

export default function AnalysePage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-6xl space-y-3 px-3 py-4">
          <AnalysisSkeleton className="h-8 w-48" />
          <AnalysisSkeleton className="h-24 w-full" />
          <AnalysisSkeleton className="h-64 w-full" />
        </div>
      }
    >
      <AnalyseWorkspace />
    </Suspense>
  );
}
