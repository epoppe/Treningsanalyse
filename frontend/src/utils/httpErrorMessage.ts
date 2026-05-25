/** Trekker ut lesbar feilmelding fra Axios/FastAPI-respons. */
export function messageFromApiError(err: unknown): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const data = (err as { response?: { data?: { detail?: unknown; message?: unknown } } }).response
      ?.data;
    const d = data?.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) {
      const parts = d.map((x: { msg?: string }) => x.msg).filter(Boolean);
      if (parts.length) return parts.join(' ');
    }
    const m = data?.message;
    if (typeof m === 'string') return m;
  }
  if (err instanceof Error && err.message) return err.message;
  return 'Kunne ikke fullføre forespørselen. Sjekk nettverk og at API kjører.';
}
