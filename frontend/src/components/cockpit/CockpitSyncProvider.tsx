"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import type { PostSyncSummaryPayload, WhatChangedPayload } from "@/types/dashboard";

export type SyncToastTone = "info" | "success" | "warning";

export interface SyncToastMessage {
  id: string;
  title: string;
  description?: string;
  tone?: SyncToastTone;
}

interface CockpitSyncContextValue {
  messages: SyncToastMessage[];
  pushToast: (message: Omit<SyncToastMessage, "id">) => void;
  dismissToast: (id: string) => void;
  postSyncSummary: PostSyncSummaryPayload | null;
  setPostSyncSummary: (summary: PostSyncSummaryPayload | null) => void;
  lastWhatChanged: WhatChangedPayload | null;
  setLastWhatChanged: (delta: WhatChangedPayload | null) => void;
}

const CockpitSyncContext = createContext<CockpitSyncContextValue | null>(null);

const toneStyles: Record<SyncToastTone, string> = {
  info: "border-slate-200 bg-white text-slate-900",
  success: "border-emerald-200 bg-emerald-50 text-emerald-950",
  warning: "border-amber-200 bg-amber-50 text-amber-950",
};

export function CockpitSyncProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = useState<SyncToastMessage[]>([]);
  const [postSyncSummary, setPostSyncSummary] = useState<PostSyncSummaryPayload | null>(null);
  const [lastWhatChanged, setLastWhatChanged] = useState<WhatChangedPayload | null>(null);

  const dismissToast = useCallback((id: string) => {
    setMessages((prev) => prev.filter((m) => m.id !== id));
  }, []);

  const pushToast = useCallback(
    (message: Omit<SyncToastMessage, "id">) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      setMessages((prev) => [...prev, { ...message, id }].slice(-3));
      window.setTimeout(() => dismissToast(id), 8000);
    },
    [dismissToast],
  );

  const value = useMemo(
    () => ({
      messages,
      pushToast,
      dismissToast,
      postSyncSummary,
      setPostSyncSummary,
      lastWhatChanged,
      setLastWhatChanged,
    }),
    [messages, pushToast, dismissToast, postSyncSummary, lastWhatChanged],
  );

  return (
    <CockpitSyncContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-0 top-16 z-50 flex flex-col items-center gap-2 px-4 md:items-end md:pr-6"
        aria-live="polite"
      >
        {messages.map((message) => (
          <div
            key={message.id}
            className={cn(
              "pointer-events-auto w-full max-w-sm rounded-xl border px-4 py-3 shadow-lg",
              toneStyles[message.tone || "info"],
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold">{message.title}</p>
                {message.description ? (
                  <p className="mt-1 text-xs opacity-90">{message.description}</p>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => dismissToast(message.id)}
                className="text-xs font-medium opacity-70 hover:opacity-100"
              >
                Lukk
              </button>
            </div>
          </div>
        ))}
      </div>
    </CockpitSyncContext.Provider>
  );
}

export function useCockpitSync() {
  const ctx = useContext(CockpitSyncContext);
  if (!ctx) {
    throw new Error("useCockpitSync must be used within CockpitSyncProvider");
  }
  return ctx;
}
