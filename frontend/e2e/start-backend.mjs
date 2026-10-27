import { spawn, spawnSync } from "node:child_process";
import { existsSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const directory = path.dirname(fileURLToPath(import.meta.url));
const backend = path.resolve(directory, "../../backend");
const port = process.env.EVALFORGE_E2E_API_PORT ?? "8001";
const token = process.env.EVALFORGE_E2E_TOKEN ?? "evalforge-e2e-token";

const localCandidates =
  process.platform === "win32"
    ? [path.join(backend, ".venv/Scripts/python.exe")]
    : [path.join(backend, ".venv/bin/python")];
const python =
  [process.env.EVALFORGE_E2E_PYTHON, ...localCandidates].find(
    (candidate) => candidate && existsSync(candidate),
  ) ?? (process.platform === "win32" ? "python" : "python3");

for (const suffix of ["", "-shm", "-wal"]) {
  rmSync(path.join(backend, `e2e.db${suffix}`), { force: true });
}

const environment = {
  ...process.env,
  EVALFORGE_ENVIRONMENT: "test",
  EVALFORGE_DATABASE_URL: "sqlite+aiosqlite:///./e2e.db",
  EVALFORGE_DEMO_MODE: "false",
  EVALFORGE_WRITE_API_TOKEN: token,
  EVALFORGE_CORS_ORIGINS: '["http://127.0.0.1:3001"]',
};

const migration = spawnSync(python, ["-m", "alembic", "upgrade", "head"], {
  cwd: backend,
  env: environment,
  stdio: "inherit",
});
if (migration.status !== 0) {
  process.exit(migration.status ?? 1);
}

const server = spawn(
  python,
  ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port],
  { cwd: backend, env: environment, stdio: "inherit" },
);

function shutdown() {
  if (!server.killed) server.kill("SIGTERM");
  setTimeout(() => {
    if (!server.killed) server.kill("SIGKILL");
  }, 3000).unref();
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
server.on("exit", (code) => process.exit(code ?? 0));
