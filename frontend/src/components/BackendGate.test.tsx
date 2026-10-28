import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getBackendState, resetBackendForTests } from "@/lib/backend";
import { BackendGate } from "./BackendGate";

vi.mock("next/image", () => ({
  default: (props: { src: string; alt: string; width: number; height: number }) => (
    <img src={props.src} alt={props.alt} width={props.width} height={props.height} />
  ),
}));

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("BackendGate", () => {
  beforeEach(() => {
    resetBackendForTests();
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    resetBackendForTests();
  });

  it("opens the live dashboard when the API answers during the probe", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ status: "ok" })));

    render(
      <BackendGate>
        <div>Live dashboard</div>
      </BackendGate>,
    );

    expect(await screen.findByText("Live dashboard")).toBeInTheDocument();
    expect(getBackendState().mode).toBe("live");
  });

  it("falls back to the recorded demo after the wake timeout", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("connection refused")));

    render(
      <BackendGate timeoutMs={40}>
        <div>Recorded dashboard</div>
      </BackendGate>,
    );

    expect(screen.getByText("Contacting the live API")).toBeInTheDocument();
    expect(screen.queryByText("Recorded dashboard")).not.toBeInTheDocument();

    expect(await screen.findByText("Recorded dashboard")).toBeInTheDocument();
    await waitFor(() => expect(getBackendState().mode).toBe("recorded"));
    expect(getBackendState().reason).toBe("waking_timeout");
  });

  it("lets the user open the recorded demo immediately", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => new Promise(() => undefined)));

    render(
      <BackendGate>
        <div>Recorded dashboard</div>
      </BackendGate>,
    );

    await user.click(screen.getByRole("button", { name: "Use recorded demo now" }));

    expect(getBackendState().mode).toBe("recorded");
    expect(getBackendState().reason).toBe("manual");
    expect(screen.getByText("Recorded dashboard")).toBeInTheDocument();
  });

  it("switches to the recorded demo when the API pauses live runs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            detail: {
              code: "live_runs_paused",
              reason: "daily",
              message: "Live runs are paused.",
            },
          },
          429,
        ),
      ),
    );

    render(
      <BackendGate>
        <div>Recorded dashboard</div>
      </BackendGate>,
    );

    expect(await screen.findByText("Recorded dashboard")).toBeInTheDocument();
    expect(getBackendState().mode).toBe("recorded");
    expect(getBackendState().reason).toBe("rate_limited");
  });
});
