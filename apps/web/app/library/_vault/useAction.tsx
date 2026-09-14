"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { VaultActionError } from "@/lib/vault";

/**
 * Run one vault action, show what happened, and refresh the server view.
 *
 * Errors keep the API's own words (and remediation) - a stale edit says the
 * record changed; a refused input says why.
 */
export function useAction() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const run = useCallback(
    async <T,>(work: () => Promise<T>, success?: string): Promise<T | null> => {
      setBusy(true);
      setError(null);
      setDone(null);
      try {
        const result = await work();
        if (success) setDone(success);
        router.refresh();
        return result;
      } catch (cause) {
        if (cause instanceof VaultActionError) {
          setError(cause.remediation ? `${cause.message} ${cause.remediation}` : cause.message);
        } else {
          setError(String(cause));
        }
        return null;
      } finally {
        setBusy(false);
      }
    },
    [router],
  );

  return { busy, error, done, run, setError };
}

export function Feedback({ error, done }: { error: string | null; done: string | null }) {
  if (error) return <p className="error-text" role="alert">{error}</p>;
  if (done) return <p className="ok-text" role="status">{done}</p>;
  return null;
}
