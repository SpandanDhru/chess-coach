"use strict";

const { app, BrowserWindow } = require("electron");
const { spawn } = require("node:child_process");
const path = require("node:path");
const http = require("node:http");
const fs = require("node:fs");

// The Python sidecar and this process must agree on the API address.
const API_HOST = process.env.API_HOST || "127.0.0.1";
const API_PORT = Number(process.env.API_PORT || 8765);
const API_BASE = `http://${API_HOST}:${API_PORT}`;

// Repo root is one level up from desktop/.
const REPO_ROOT = path.resolve(__dirname, "..", "..");

let sidecar = null;
let mainWindow = null;

/** Pick the repo virtualenv's Python if present, else fall back to PATH. */
function resolvePython() {
  const venvPython = path.join(REPO_ROOT, ".venv", "bin", "python");
  if (fs.existsSync(venvPython)) return venvPython;
  return process.env.PYTHON || "python3";
}

function startSidecar() {
  const python = resolvePython();
  sidecar = spawn(python, ["-m", "src.api"], {
    cwd: REPO_ROOT,
    env: { ...process.env, API_HOST, API_PORT: String(API_PORT) },
    stdio: "inherit",
  });
  sidecar.on("exit", (code) => {
    console.log(`[sidecar] exited with code ${code}`);
    sidecar = null;
  });
}

/** Resolve once the sidecar answers /api/health (polls up to ~30s). */
function waitForApi(timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const poll = () => {
      http
        .get(`${API_BASE}/api/health`, (res) => {
          res.resume();
          if (res.statusCode === 200) return resolve();
          retry();
        })
        .on("error", retry);
    };
    const retry = () => {
      if (Date.now() > deadline) return reject(new Error("API did not start in time"));
      setTimeout(poll, 400);
    };
    poll();
  });
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#0a0a0a",
    title: "Chess Coach",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) {
    await mainWindow.loadURL(devUrl);
  } else {
    await mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

app.whenReady().then(async () => {
  startSidecar();
  try {
    await waitForApi();
  } catch (err) {
    console.error(err.message);
  }
  await createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

function stopSidecar() {
  if (sidecar) {
    sidecar.kill();
    sidecar = null;
  }
}

app.on("window-all-closed", () => {
  stopSidecar();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", stopSidecar);
process.on("exit", stopSidecar);
