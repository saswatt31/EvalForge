"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useSyncExternalStore, type FormEvent, type ReactNode } from "react";

import {
  API_DOCS_URL,
  hasWriteToken,
  setWriteToken,
  subscribeWriteToken,
} from "@/lib/api";
import { retryBackend, useBackendState, type RecordedReason } from "@/lib/backend";
import { useMeta } from "@/lib/hooks";
import {
  CloseIcon,
  CompareIcon,
  DatasetIcon,
  ExternalIcon,
  GridIcon,
  LockIcon,
  MenuIcon,
  RunsIcon,
} from "./icons";

const navigation = [
  { href: "/", label: "Overview", icon: GridIcon },
  { href: "/runs", label: "Runs", icon: RunsIcon },
  { href: "/datasets", label: "Datasets", icon: DatasetIcon },
  { href: "/compare", label: "Compare", icon: CompareIcon },
];

const noStoredToken = () => false;

function recordedReasonMessage(reason: RecordedReason | null): string {
  if (reason === "rate_limited") return "The free-tier live-run budget is exhausted right now.";
  if (reason === "waking_timeout") return "The free-tier API did not wake up in time.";
  if (reason === "unreachable") return "The live API is unreachable.";
  return "You opened the recorded demo.";
}

function pageTitle(pathname: string): string {
  if (pathname === "/") return "Overview";
  if (pathname === "/runs/new") return "New evaluation";
  if (pathname.startsWith("/runs/")) return "Run detail";
  if (pathname === "/runs") return "Runs";
  if (pathname.startsWith("/datasets/")) return "Dataset";
  if (pathname === "/datasets") return "Datasets";
  if (pathname === "/compare") return "Compare";
  return "EvalForge";
}

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function WriteAccess({ demoMode }: { demoMode: boolean }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const saved = useSyncExternalStore(subscribeWriteToken, hasWriteToken, noStoredToken);

  if (demoMode) {
    return (
      <div className="access-note">
        <LockIcon />
        <span>Read-only demo</span>
      </div>
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setWriteToken(value);
    setValue("");
    setOpen(false);
  }

  return (
    <div className="access-control">
      <button
        className="access-trigger"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <LockIcon />
        <span>{saved ? "Token set" : "Write access"}</span>
        <span className={`access-dot ${saved ? "on" : ""}`} aria-hidden="true" />
      </button>
      {open ? (
        <form className="access-form" onSubmit={submit}>
          <label htmlFor="write-token">Write API token</label>
          <input
            id="write-token"
            type="password"
            autoComplete="off"
            placeholder="X-API-Key value"
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
          <p>Stored only in this browser tab&apos;s session storage.</p>
          <div className="access-actions">
            <button className="button small primary" type="submit">
              Save token
            </button>
            <button
              className="button small ghost"
              type="button"
              onClick={() => {
                setWriteToken("");
                setValue("");
              }}
            >
              Clear
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data: meta, error: metaError } = useMeta();
  const backend = useBackendState();
  const recorded = backend.mode === "recorded";
  const [menuPath, setMenuPath] = useState<string | null>(null);
  const menuOpen = menuPath === pathname;
  const title = pageTitle(pathname);

  return (
    <div className="app-frame">
      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <div className="sidebar-top">
          <Link className="brand" href="/" aria-label="EvalForge overview">
            <Image src="/evalforge-mark.svg" alt="" width={34} height={34} priority />
            <span>
              EvalForge
              <small>RAG evaluation lab</small>
            </span>
          </Link>
          <button
            className="icon-button mobile-only"
            type="button"
            aria-label="Close navigation"
            onClick={() => setMenuPath(null)}
          >
            <CloseIcon />
          </button>
        </div>

        <nav className="sidebar-nav" aria-label="Primary">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={active ? "active" : ""}
                aria-current={active ? "page" : undefined}
              >
                <Icon />
                <span>{item.label}</span>
                {active ? <span className="nav-rail" aria-hidden="true" /> : null}
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-spacer" />

        <div className="sidebar-status">
          <div className="api-state">
            <span
              className={`api-dot ${
                recorded
                  ? "waiting"
                  : metaError
                    ? "offline"
                    : meta?.database_ready
                      ? "ready"
                      : "waiting"
              }`}
              aria-hidden="true"
            />
            <div>
              <strong>
                {recorded
                  ? "Recorded demo"
                  : metaError
                    ? "API unreachable"
                    : meta?.database_ready
                      ? "API connected"
                      : "API starting"}
              </strong>
              <span>
                {recorded
                  ? "Live API offline or paused"
                  : meta
                    ? `${meta.target_kinds.length} target kinds · v0.1`
                    : "Checking backend"}
              </span>
            </div>
          </div>
          <WriteAccess demoMode={recorded || Boolean(meta?.demo_mode)} />
          {recorded ? null : (
            <a className="docs-link" href={API_DOCS_URL} target="_blank" rel="noreferrer">
              <ExternalIcon />
              <span>API documentation</span>
            </a>
          )}
        </div>
      </aside>

      {menuOpen ? (
        <button
          className="sidebar-scrim"
          type="button"
          aria-label="Close navigation"
          onClick={() => setMenuPath(null)}
        />
      ) : null}

      <div className="app-main">
        {recorded ? (
          <div className="demo-banner recorded-banner" role="status">
            <span className="demo-pill">Recorded</span>
            <span>
              {recordedReasonMessage(backend.reason)} You are viewing committed demo data generated
              from the synthetic corpus with the deterministic mock judge. Nothing on this screen is
              a live run or a live measurement.
            </span>
            <button className="button tiny ghost" type="button" onClick={retryBackend}>
              Retry live backend
            </button>
          </div>
        ) : meta?.demo_mode ? (
          <div className="demo-banner" role="status">
            <span className="demo-pill">Demo</span>
            This deployment is read-only. Benchmark values are synthetic and generated from the
            bundled corpus with a deterministic mock judge.
          </div>
        ) : null}
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-button mobile-only"
              type="button"
              aria-label="Open navigation"
              onClick={() => setMenuPath(pathname)}
            >
              <MenuIcon />
            </button>
            <span className="topbar-title">{title}</span>
          </div>
          <div className="topbar-right">
            <span className="topbar-label">Quality + latency evidence</span>
            <Link className="button primary small" href="/runs/new">
              New run
            </Link>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
