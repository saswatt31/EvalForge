import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  API_BASE,
  ApiError,
  apiGet,
  apiPost,
  getWriteToken,
  hasWriteToken,
  setWriteToken,
  subscribeWriteToken,
} from "./api";
import { activateRecorded, resetBackendForTests } from "./backend";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("API client", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    resetBackendForTests();
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });

  it("calls the versioned API with JSON accept headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ demo_mode: false }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiGet<{ demo_mode: boolean }>("/meta");

    expect(result.demo_mode).toBe(false);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${API_BASE}/meta`);
    expect(init.cache).toBe("no-store");
    const headers = new Headers(init.headers);
    expect(headers.get("Accept")).toBe("application/json");
    expect(headers.get("X-API-Key")).toBeNull();
  });

  it("adds the session write token to every request", async () => {
    setWriteToken("  secret-token  ");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiGet("/runs");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get("X-API-Key")).toBe("secret-token");
  });

  it("normalizes validation errors into an ApiError", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          detail: [{ loc: ["body", "name"], msg: "Field required" }],
        },
        422,
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const error = await apiGet("/datasets").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(422);
    expect(apiError.message).toContain("Field required");
    expect(apiError.issues).toEqual([{ field: "body.name", message: "Field required" }]);
  });

  it("supports structured error details with nested issues", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            detail: {
              message: "Dataset import rejected",
              errors: [{ field: "line", message: "line 4 is invalid JSON" }],
            },
          },
          400,
        ),
      ),
    );

    const error = await apiGet("/datasets").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("Dataset import rejected");
    expect((error as ApiError).issues).toEqual([
      { field: "line", message: "line 4 is invalid JSON" },
    ]);
  });

  it("turns transport failures into a reachable help message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network down")));

    const error = await apiGet("/meta").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
    expect((error as ApiError).message).toContain("Could not reach the EvalForge API");
  });

  it("returns undefined for 204 responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));

    await expect(apiGet("/runs/example/cancel")).resolves.toBeUndefined();
  });

  it("serves recorded data without touching the network once the demo is active", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    activateRecorded("rate_limited");

    const runs = await apiGet<{ total: number; items: Array<{ source: string }> }>(
      "/runs?limit=10",
    );

    expect(runs.total).toBe(2);
    expect(runs.items.every((run) => run.source === "demo")).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects writes in recorded mode with a read-only error", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    activateRecorded("waking_timeout");

    const error = await apiPost("/runs", {}).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(403);
    expect((error as ApiError).message).toContain("recorded demo");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("notifies subscribers when the write token changes", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeWriteToken(listener);

    expect(hasWriteToken()).toBe(false);
    setWriteToken("abc");
    expect(getWriteToken()).toBe("abc");
    expect(hasWriteToken()).toBe(true);
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    setWriteToken("");
    expect(listener).toHaveBeenCalledTimes(1);
    expect(getWriteToken()).toBe("");
  });
});
