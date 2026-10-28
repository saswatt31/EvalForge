"use client";

import Image from "next/image";
import { useEffect, type ReactNode } from "react";

import { API_BASE } from "@/lib/api";
import {
  activateRecorded,
  markBackendLive,
  markBackendWaking,
  retryBackend,
  useBackendState,
  WAKE_TIMEOUT_MS,
} from "@/lib/backend";

const PROBE_INTERVAL_MS = 2_000;
const PROBE_REQUEST_TIMEOUT_MS = 5_000;
const RETRYABLE_STATUS = new Set([502, 503, 504]);

function WakingScreen({
  waking,
  timeoutMs,
  onUseRecorded,
}: {
  waking: boolean;
  timeoutMs: number;
  onUseRecorded: () => void;
}) {
  const seconds = Math.max(1, Math.round(timeoutMs / 1_000));
  return (
    <main className="boot-screen" data-testid="backend-boot">
      <div className="boot-card" role="status" aria-live="polite">
        <div className="boot-brand">
          <Image src="/evalforge-mark.svg" alt="" width={44} height={44} priority />
          <div>
            <strong>EvalForge</strong>
            <span>RAG evaluation lab</span>
          </div>
        </div>
        <span className="spinner boot-spinner" aria-hidden="true" />
        <h1>{waking ? "Waking the live API" : "Contacting the live API"}</h1>
        <p>
          {waking
            ? "The free-tier backend sleeps after inactivity. A cold start usually takes 30-60 seconds."
            : "Checking whether the API is already running."}
        </p>
        <p className="boot-timeout">
          If it does not respond within {seconds} seconds, the dashboard opens the committed
          recorded demo automatically.
        </p>
        <div className="boot-actions">
          <button className="button secondary small" type="button" onClick={onUseRecorded}>
            Use recorded demo now
          </button>
        </div>
        <small>
          Recorded values are synthetic and were generated with the deterministic mock judge. They
          are never presented as live measurements.
        </small>
      </div>
    </main>
  );
}

export function BackendGate({
  children,
  timeoutMs = WAKE_TIMEOUT_MS,
}: {
  children: ReactNode;
  timeoutMs?: number;
}) {
  const state = useBackendState();
  const booting = state.mode === "probing" || state.mode === "waking";

  useEffect(() => {
    if (!booting) return;

    let cancelled = false;
    let timer: number | undefined;
    let controller: AbortController | undefined;
    const deadline = Date.now() + timeoutMs;

    async function probe(): Promise<void> {
      if (cancelled) return;
      controller = new AbortController();
      const requestTimer = window.setTimeout(
        () => controller?.abort(),
        Math.min(PROBE_REQUEST_TIMEOUT_MS, timeoutMs),
      );
      try {
        const response = await fetch(`${API_BASE}/meta`, {
          signal: controller.signal,
          cache: "no-store",
          headers: { Accept: "application/json" },
        });
        window.clearTimeout(requestTimer);
        if (cancelled) return;

        if (response.ok) {
          markBackendLive();
          return;
        }

        let detail: unknown = null;
        try {
          const body = (await response.json()) as Record<string, unknown>;
          detail = body.detail ?? body;
        } catch {
          detail = null;
        }
        const record =
          detail && typeof detail === "object" ? (detail as Record<string, unknown>) : null;
        if (response.status === 429 && record?.code === "live_runs_paused") {
          activateRecorded("rate_limited");
          return;
        }
        if (!RETRYABLE_STATUS.has(response.status)) {
          // The API answered. Let individual pages show its validation or server error.
          markBackendLive();
          return;
        }
      } catch {
        if (cancelled) return;
      } finally {
        window.clearTimeout(requestTimer);
      }

      if (cancelled) return;
      markBackendWaking();
      if (Date.now() >= deadline) {
        activateRecorded("waking_timeout");
        return;
      }
      timer = window.setTimeout(
        () => void probe(),
        Math.min(PROBE_INTERVAL_MS, Math.max(250, deadline - Date.now())),
      );
    }

    void probe();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
      controller?.abort();
    };
  }, [booting, state.attempt, timeoutMs]);

  if (booting) {
    return (
      <WakingScreen
        waking={state.mode === "waking"}
        timeoutMs={timeoutMs}
        onUseRecorded={() => activateRecorded("manual")}
      />
    );
  }

  return <>{children}</>;
}

export function RetryLiveButton() {
  return (
    <button className="button tiny ghost" type="button" onClick={retryBackend}>
      Retry live backend
    </button>
  );
}
