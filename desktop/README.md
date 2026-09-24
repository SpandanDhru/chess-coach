# Chess Coach — Desktop UI

A retro 8-bit desktop app (Claude Code / OpenCode aesthetic) for the Chess Coach:
a beige/brown pixel chessboard on the left, an OpenCode-style terminal chat on the
right, and pixel piece icons rendered wherever the coach names a piece.

## Architecture

```
Electron main  ──spawns──▶  Python FastAPI sidecar (src/api, 127.0.0.1:8765)
     │                          reuses Coach / Knowledge / Database / analyzers
     └─loads──▶ React renderer ─── HTTP/JSON ──▶ the sidecar
```

The Python backend is the source of truth — the UI only renders and calls HTTP.

## Prerequisites

- The Python project set up and working (`.venv` with `pip install -r requirements.txt`,
  a valid `.env` with `OPENAI_API_KEY`, and Stockfish installed). Verify with the CLI:
  `python -m src.cli stats`.
- **Node.js 18+ installed *inside* your Linux/WSL environment** and run from a Linux
  shell — **not** the Windows `node`/`npm`.

> ### WSL users — read this first
> If you installed the project under `\\wsl.localhost\...`, you **must** use a Linux Node,
> not the Windows one. Running Windows `npm install` against WSL files fails with
> `UNC paths are not supported` / `Cannot find module 'C:\Windows\install.js'` when Electron
> tries to post-install. Fix:
> ```bash
> # in an Ubuntu (WSL) shell:
> curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
> # reopen the shell, then:
> nvm install --lts        # installs Linux Node + npm
> node -v                  # should print a Linux node, e.g. v20.x
> # clean up the half-written Windows install and reinstall:
> cd desktop && rm -rf node_modules package-lock.json && npm install
> ```

## Browser mode (simplest — no Electron)

Because the renderer talks to the API over HTTP, you can run it in a normal browser with no
Electron at all. From `desktop/`:

```bash
npm run web
```

This starts the Python API **and** the Vite dev server together. Open
**http://localhost:5173** in your browser (on WSL, your Windows browser can reach it). This
avoids Electron's WSL GUI requirements and is the fastest way to see the app.

## Run as a desktop app (Electron)

From this `desktop/` folder:

```bash
npm install        # first time only (Linux node — see WSL note above)
npm run dev
```

`npm run dev` starts the Vite dev server and Electron together; Electron launches
the Python sidecar itself (using `../.venv/bin/python -m src.api`) and waits for it
to be healthy before showing the window.

On **WSL**, the Electron window needs GUI support: WSLg (built into WSL2 on Windows 11)
works out of the box; on Windows 10 you'd need an X server. Electron may also require a few
system libs — if the window fails to open, install them:
`sudo apt install -y libnss3 libatk-bridge2.0-0 libgbm1 libasound2 libgtk-3-0`.
If any of that is a hassle, just use **browser mode** (`npm run web`) above.

You should see: the gate screen → pick Chess.com/Lichess + type a username → a retro
loading bar (sync → analyze → index) → the board + terminal workspace.

## Notes

- The sidecar bind address comes from `API_HOST` / `API_PORT` in your `.env`
  (defaults `127.0.0.1:8765`); Electron reads the same values.
- Piece icons in coach text are driven by `{{wN}}`-style tokens the API's LLM emits
  (the CLI never emits them, so terminal output stays clean).
- Board is **static-position mode** for now (renders a position; jumps to a game's key
  moment when you review it). Move-by-move step-through is a planned next iteration.
- Packaging into a single distributable binary (bundling the Python sidecar via
  PyInstaller + electron-builder) is not set up yet — this is a dev-run app for now.

## Backend only (no Electron)

You can run just the API for testing:

```bash
# from the repo root
python -m src.api
# then: curl http://127.0.0.1:8765/api/health
```
