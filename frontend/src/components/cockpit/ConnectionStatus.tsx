"use client";

import { useEffect, useState } from "react";

type ProbeState = "checking" | "online" | "offline";

export function ConnectionStatus({
  online,
  asOf,
}: {
  online?: boolean;
  asOf?: string;
}) {
  const [probe, setProbe] = useState<ProbeState>(
    online === false ? "offline" : online === true ? "online" : "checking",
  );

  useEffect(() => {
    if (online === false) {
      setProbe("offline");
      return;
    }
    let cancelled = false;
    const ping = async () => {
      try {
        const res = await fetch("/health/live", { cache: "no-store" });
        if (!cancelled) setProbe(res.ok ? "online" : "offline");
      } catch {
        if (!cancelled) setProbe("offline");
      }
    };
    void ping();
    const id = window.setInterval(ping, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [online]);

  if (probe === "offline" || online === false) {
    return (
      <p
        role="status"
        className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] font-medium text-rose-800"
      >
        Treningsanalyse-serveren er ikke tilgjengelig. Start backend (
        <code className="font-mono">npm run start:backend</code>) og prøv igjen.
      </p>
    );
  }

  if (probe === "checking") {
    return (
      <p className="text-[11px] text-slate-500" role="status">
        Sjekker tilkobling…
      </p>
    );
  }

  const timeLabel = asOf ? asOf.slice(0, 16).replace("T", " ") : null;

  return (
    <p className="text-[11px] text-slate-500" role="status">
      Connected{timeLabel ? ` · As of ${timeLabel}` : ""}
    </p>
  );
}
