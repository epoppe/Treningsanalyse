"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import ActivityAnalytics from "@/components/ActivityAnalytics";
import ActivityDetailsCharts from "@/components/ActivityDetailsCharts";
import { ComparableSessionsSection } from "@/components/cockpit/ComparableSessionsCard";
import type { AsyncLoadState } from "@/utils/metricState";

function InterpretationBlock({
  title,
  eyebrow,
  children,
}: {
  title: string;
  eyebrow: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        {eyebrow}
      </p>
      <h2 className="mt-1 text-lg font-semibold text-slate-900">{title}</h2>
      <div className="mt-2 text-sm text-slate-700">{children}</div>
    </section>
  );
}

const ActivityDetailPage = () => {
  const params = useParams();
  const id = Number(params.id);
  const [detailsState, setDetailsState] = useState<AsyncLoadState>("loading");
  const [detailsData, setDetailsData] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id || Number.isNaN(id)) return;

    const controller = new AbortController();

    const fetchDetails = async () => {
      setDetailsState("loading");
      setError(null);

      try {
        const response = await fetch(`/api/activities/${id}/details`, {
          signal: controller.signal,
        });

        if (response.status === 404) {
          setDetailsData([]);
          setDetailsState("missing");
          return;
        }

        if (!response.ok) {
          throw new Error(`API-feil (${response.status}): ${response.statusText}`);
        }

        const data = await response.json();
        if (!Array.isArray(data) || data.length === 0) {
          setDetailsData([]);
          setDetailsState("missing");
          return;
        }

        setDetailsData(data);
        setDetailsState("ready");
      } catch (err) {
        if (controller.signal.aborted) return;
        setDetailsState("error");
        if (err instanceof Error) setError(err.message);
        else setError("En ukjent feil oppstod ved henting av aktivitetsdetaljer");
      }
    };

    void fetchDetails();
    return () => controller.abort();
  }, [id]);

  if (Number.isNaN(id)) {
    return <p className="p-4 text-sm text-slate-600">Ugyldig aktivitets-ID.</p>;
  }

  if (detailsState === "loading") {
    return <p className="p-4 text-sm text-slate-600">Laster aktivitetsdetaljer…</p>;
  }

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-4 md:p-10">
      <header>
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
          Øktdetalj
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
          Aktivitet {id}
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Tolkning først — tekniske grafer til slutt.
        </p>
      </header>

      <InterpretationBlock eyebrow="What was this session?" title="Klassifisering">
        <p>
          Session type og struktur vurderes av coaching-/analysebackend. Frontend lager ikke egne
          anbefalinger.
        </p>
      </InterpretationBlock>

      <InterpretationBlock eyebrow="How well did it go?" title="Session quality & execution">
        <ActivityAnalytics activityId={id} />
      </InterpretationBlock>

      <InterpretationBlock eyebrow="How did it compare?" title="Comparable sessions">
        <ComparableSessionsSection activityId={String(id)} />
      </InterpretationBlock>

      <InterpretationBlock eyebrow="What did it cost?" title="Recovery cost">
        <p>
          Restitusjonskostnad vurderes via HRV/belastning.{" "}
          <Link
            href="/analyse?tab=utvikling&metrics=cardio.hrv_7d,fitness.atl"
            className="underline"
          >
            Åpne restitusjon i analyse
          </Link>
        </p>
      </InterpretationBlock>

      <InterpretationBlock eyebrow="What does it mean?" title="Plan / recommendation impact">
        <p>
          Se «Since last update» på I dag etter sync.{" "}
          <Link href="/" className="underline">
            Tilbake til I dag
          </Link>
        </p>
      </InterpretationBlock>

      {detailsState === "error" ? (
        <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          Feil ved henting av aktivitetsdetaljer: {error}
        </p>
      ) : null}

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-900">Tekniske grafer</h2>
        <ActivityDetailsCharts detailsState={detailsState} detailsData={detailsData} />
      </section>
    </main>
  );
};

export default ActivityDetailPage;
