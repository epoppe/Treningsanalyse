"use client";

import { useCallback, useEffect, useState } from "react";
import { useAnalysisUrlState } from "@/components/analysis/AnalysisShell";

const STORAGE_KEY = "treningsanalyse.analysis.bookmarks";

type Bookmark = {
  id: string;
  label: string;
  href: string;
  createdAt: string;
};

function loadBookmarks(): Bookmark[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Bookmark[]) : [];
  } catch {
    return [];
  }
}

export function SavedAnalysisViews() {
  const { state } = useAnalysisUrlState();
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [label, setLabel] = useState("");

  useEffect(() => {
    setBookmarks(loadBookmarks());
  }, []);

  const persist = useCallback((next: Bookmark[]) => {
    setBookmarks(next);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }, []);

  const saveCurrent = () => {
    const params = new URLSearchParams();
    params.set("tab", state.tab);
    params.set("period", state.period);
    if (state.metrics.length) params.set("metrics", state.metrics.join(","));
    if (state.outcome) params.set("outcome", state.outcome);
    if (state.week) params.set("week", state.week);
    const href = `/analyse?${params.toString()}`;
    const entry: Bookmark = {
      id: `${Date.now()}`,
      label: label.trim() || `${state.tab} · ${state.period}`,
      href,
      createdAt: new Date().toISOString(),
    };
    persist([entry, ...bookmarks].slice(0, 8));
    setLabel("");
  };

  const remove = (id: string) => {
    persist(bookmarks.filter((b) => b.id !== id));
  };

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">Lagrede analyser</h2>
      <p className="mt-0.5 text-[11px] text-slate-500">
        Bokmerker lagres lokalt i nettleseren — delbar via URL.
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Navn på visning"
          className="min-w-[160px] flex-1 rounded-md border border-slate-200 px-2 py-1 text-sm"
        />
        <button
          type="button"
          onClick={saveCurrent}
          className="rounded-md bg-slate-900 px-3 py-1 text-sm font-medium text-white"
        >
          Lagre visning
        </button>
      </div>
      {bookmarks.length ? (
        <ul className="mt-3 space-y-1">
          {bookmarks.map((bookmark) => (
            <li
              key={bookmark.id}
              className="flex items-center justify-between gap-2 rounded-md border border-slate-100 px-2 py-1.5 text-xs"
            >
              <a href={bookmark.href} className="font-medium text-slate-800 underline">
                {bookmark.label}
              </a>
              <button
                type="button"
                onClick={() => remove(bookmark.id)}
                className="text-slate-500 underline"
              >
                Fjern
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-slate-500">Ingen lagrede visninger ennå.</p>
      )}
    </section>
  );
}
