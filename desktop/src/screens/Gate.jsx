import React, { useEffect, useRef, useState } from "react";
import { api } from "../lib/api.js";

const PHASES = ["validating", "syncing", "analyzing", "indexing", "ready"];

function AsciiBar({ done, total, width = 24 }) {
  const ratio = total > 0 ? Math.min(1, done / total) : 0;
  const filled = Math.round(ratio * width);
  return (
    <span className="accent">
      [{"■".repeat(filled)}
      {"□".repeat(width - filled)}]
    </span>
  );
}

export default function Gate({ onReady }) {
  const [platform, setPlatform] = useState("chesscom");
  const [username, setUsername] = useState("");
  const [job, setJob] = useState(null); // {state, phase, done, total, message, error}
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState([]);
  const pollRef = useRef(null);
  const seenPhase = useRef(new Set());

  useEffect(() => () => clearInterval(pollRef.current), []);

  function appendLog(line) {
    setLog((l) => [...l, line]);
  }

  async function submit() {
    if (!username.trim() || busy) return;
    setError(null);
    setLog([]);
    seenPhase.current = new Set();
    setBusy(true);
    appendLog(`> connecting to ${platform} as "${username.trim()}"...`);
    try {
      const { job_id } = await api.startSession(platform, username.trim());
      pollRef.current = setInterval(() => poll(job_id), 500);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  async function poll(jobId) {
    try {
      const s = await api.getSession(jobId);
      setJob(s);
      if (s.phase && !seenPhase.current.has(s.phase)) {
        seenPhase.current.add(s.phase);
        appendLog(`> ${s.phase}...`);
      }
      if (s.state === "ready") {
        clearInterval(pollRef.current);
        appendLog("> ready.");
        setTimeout(() => onReady({ username: username.trim(), platform }), 350);
      } else if (s.state === "error") {
        clearInterval(pollRef.current);
        setError(s.error || "Sync failed.");
        setBusy(false);
      }
    } catch (e) {
      clearInterval(pollRef.current);
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <div style={wrap}>
      <div style={{ width: 620 }}>
        <pre style={logo} className="accent">{` ██████╗██╗  ██╗███████╗███████╗███████╗
██╔════╝██║  ██║██╔════╝██╔════╝██╔════╝
██║     ███████║█████╗  ███████╗███████╗
██║     ██╔══██║██╔══╝  ╚════██║╚════██║
╚██████╗██║  ██║███████╗███████║███████║
 ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝
 ██████╗ ██████╗  █████╗  ██████╗██╗  ██╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝██║  ██║
██║     ██║   ██║███████║██║     ███████║
██║     ██║   ██║██╔══██║██║     ██╔══██║
╚██████╗╚██████╔╝██║  ██║╚██████╗██║  ██║
 ╚═════╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝`}</pre>
        <div className="dim" style={{ marginBottom: 20, textAlign: "center" }}>
          retro chess coaching // stockfish + rag
        </div>

        {!busy && !job && (
          <div className="panel" style={card}>
            <div style={{ marginBottom: 14 }}>
              <span className="dim">platform:</span>{" "}
              <button
                className={platform === "chesscom" ? "active" : ""}
                onClick={() => setPlatform("chesscom")}
              >
                chess.com
              </button>{" "}
              <button
                className={platform === "lichess" ? "active" : ""}
                onClick={() => setPlatform("lichess")}
              >
                lichess
              </button>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="green">&gt;</span>
              <input
                autoFocus
                placeholder="enter your username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                style={{ flex: 1 }}
              />
              <span className="green blink">█</span>
            </div>
            <div style={{ marginTop: 16 }}>
              <button onClick={submit} disabled={!username.trim()}>
                ▶ start
              </button>
            </div>
          </div>
        )}

        {(busy || job) && (
          <div className="panel" style={card}>
            {log.map((line, i) => (
              <div key={i} className="dim" style={{ whiteSpace: "pre-wrap" }}>
                {line}
              </div>
            ))}
            {job && job.state !== "ready" && (
              <div style={{ marginTop: 10 }}>
                <AsciiBar
                  done={job.phase === "analyzing" ? job.done : phaseIndex(job.phase)}
                  total={job.phase === "analyzing" ? job.total || 1 : PHASES.length - 1}
                />{" "}
                <span className="dim">
                  {job.phase === "analyzing" && job.total
                    ? `${job.done}/${job.total} `
                    : ""}
                  {job.message}
                </span>
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="panel" style={{ ...card, borderColor: "var(--danger)" }}>
            <span className="danger">! {error}</span>
            <div style={{ marginTop: 12 }}>
              <button onClick={() => { setError(null); setJob(null); setBusy(false); }}>
                ↺ retry
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function phaseIndex(phase) {
  const i = PHASES.indexOf(phase);
  return i < 0 ? 0 : i;
}

const wrap = {
  height: "100%",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};
const logo = {
  fontSize: 11,
  lineHeight: 1.05,
  margin: "0 auto",
  textAlign: "center",
  width: "fit-content",
  textShadow: "0 0 6px rgba(224,164,88,0.35)",
};
const card = { padding: 20, marginTop: 18 };
