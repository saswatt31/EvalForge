"use client";

import { useSyncExternalStore } from "react";

export type BackendMode = "probing" | "waking" | "live" | "recorded";
export type RecordedReason =
  | "waking_timeout"
  | "unreachable"
  | "rate_limited"
  | "manual";

export interface BackendState {
  mode: BackendMode;
  reason: RecordedReason | null;
  attempt: number;
  changedAt: number;
}

const configuredTimeout = Number(process.env.NEXT_PUBLIC_BACKEND_WAKE_TIMEOUT_MS);
export const WAKE_TIMEOUT_MS =
  Number.isFinite(configuredTimeout) && configuredTimeout >= 1_000
    ? configuredTimeout
    : 20_000;

const INITIAL_STATE: BackendState = {
  mode: "probing",
  reason: null,
  attempt: 0,
  changedAt: 0,
};

let state: BackendState = INITIAL_STATE;
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((listener) => listener());
}

export function getBackendState(): BackendState {
  return state;
}

function getServerState(): BackendState {
  return INITIAL_STATE;
}

export function subscribeBackendState(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useBackendState(): BackendState {
  return useSyncExternalStore(subscribeBackendState, getBackendState, getServerState);
}

export function getBackendMode(): BackendMode {
  return state.mode;
}

export function isRecordedMode(): boolean {
  return state.mode === "recorded";
}

export function markBackendLive(): void {
  if (state.mode === "live") return;
  state = { mode: "live", reason: null, attempt: state.attempt, changedAt: Date.now() };
  emit();
}

export function markBackendWaking(): void {
  if (state.mode === "recorded" || state.mode === "waking") return;
  state = { mode: "waking", reason: null, attempt: state.attempt, changedAt: Date.now() };
  emit();
}

export function activateRecorded(reason: RecordedReason): void {
  if (state.mode === "recorded" && state.reason === reason) return;
  state = { mode: "recorded", reason, attempt: state.attempt, changedAt: Date.now() };
  emit();
}

export function retryBackend(): void {
  state = {
    mode: "probing",
    reason: null,
    attempt: state.attempt + 1,
    changedAt: Date.now(),
  };
  emit();
}

export function resetBackendForTests(): void {
  state = INITIAL_STATE;
  emit();
}
