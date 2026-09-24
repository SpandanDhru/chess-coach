import React, { useEffect, useRef, useState } from "react";
import { api } from "../lib/api.js";
import { renderPieces } from "../lib/renderPieces.jsx";

// Message kinds: "user" | "coach" | "system" | "games" | "sources"
let _id = 0;
const nextId = () => ++_id;

export default function Terminal({ username, onLoadBoard }) {
  const [messages, setMessages] = useState([
    {
      id: nextId(),
      kind: "system",
      text:
        "coach online. ask anything about your games, or type `games` and click " +
        "one to load it on the board — then step through moves and hit " +
        "`explain this move`. try: what openings do i struggle with?",
    },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages, busy]);

  function push(msg) {
    setMessages((m) => [...m, { id: nextId(), ...msg }]);
  }

  async function handle(raw) {
    const text = raw.trim();
    if (!text || busy) return;
    push({ kind: "user", text });
    setInput("");

    const lower = text.toLowerCase();
    if (lower === "games" || lower === "/games") {
      return loadGames();
    }
    const review = lower.match(/^\/?review\s+(\S+)/);
    if (review) {
      return reviewGame(review[1]);
    }
    return ask(text);
  }

  async function ask(message) {
    setBusy(true);
    try {
      const { answer, sources } = await api.chat(username, message);
      push({ kind: "coach", text: answer });
      if (sources?.length) push({ kind: "sources", sources });
    } catch (e) {
      push({ kind: "system", text: `! ${e.message}`, error: true });
    } finally {
      setBusy(false);
    }
  }

  async function loadGames() {
    setBusy(true);
    try {
      const { games } = await api.listGames(username);
      if (!games.length) {
        push({ kind: "system", text: "no games stored yet." });
      } else {
        push({ kind: "games", games });
      }
    } catch (e) {
      push({ kind: "system", text: `! ${e.message}`, error: true });
    } finally {
      setBusy(false);
    }
  }

  async function reviewGame(gameId) {
    setBusy(true);
    push({ kind: "system", text: `loading ${gameId} onto the board...` });
    // Load the game into the step-through board immediately.
    if (onLoadBoard) onLoadBoard(gameId);
    try {
      const { writeup } = await api.coachGame(gameId);
      push({ kind: "coach", text: writeup });
    } catch (e) {
      push({ kind: "system", text: `! ${e.message}`, error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={wrap}>
      <div ref={scrollRef} style={scroll}>
        {messages.map((m) => (
          <Line key={m.id} m={m} onReview={reviewGame} />
        ))}
        {busy && (
          <div className="dim">
            <span className="blink">▓</span> coach is thinking...
          </div>
        )}
      </div>
      <div style={inputRow}>
        <span className="green">&gt;</span>
        <input
          autoFocus
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handle(input)}
          placeholder="ask the coach..."
          style={{ flex: 1 }}
          disabled={busy}
        />
      </div>
    </div>
  );
}

function Line({ m, onReview }) {
  if (m.kind === "user") {
    return (
      <div style={{ marginTop: 8 }}>
        <span className="green">&gt; </span>
        <span>{m.text}</span>
      </div>
    );
  }
  if (m.kind === "coach") {
    return (
      <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>
        <span className="accent">coach:</span> {renderPieces(m.text)}
      </div>
    );
  }
  if (m.kind === "sources") {
    return (
      <details style={{ marginTop: 4 }}>
        <summary className="dim" style={{ cursor: "pointer" }}>
          retrieved context ({m.sources.length})
        </summary>
        {m.sources.map((s, i) => (
          <div key={i} className="dim" style={{ fontSize: 12, marginTop: 2 }}>
            [{s.score.toFixed(3)}] ({s.source_type}) {s.text}
          </div>
        ))}
      </details>
    );
  }
  if (m.kind === "games") {
    return (
      <div style={{ marginTop: 6 }}>
        <span className="dim">your games (click to review):</span>
        {m.games.map((g) => (
          <div
            key={g.game_id}
            onClick={() => g.analyzed && onReview(g.game_id)}
            style={{
              cursor: g.analyzed ? "pointer" : "default",
              opacity: g.analyzed ? 1 : 0.5,
              padding: "2px 0",
            }}
            className="gameRow"
          >
            <span className="accent">{g.game_id}</span>{" "}
            <span className="dim">
              {g.color} vs {g.opponent} · {g.result} · {g.opening || "?"}
              {g.analyzed ? "" : " · (not analyzed)"}
            </span>
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className={m.error ? "danger" : "dim"} style={{ marginTop: 6 }}>
      {m.text}
    </div>
  );
}

const wrap = {
  display: "flex",
  flexDirection: "column",
  height: "100%",
  background: "var(--bg-panel)",
  border: "1px solid var(--border)",
};
const scroll = { flex: 1, overflowY: "auto", padding: 16 };
const inputRow = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  padding: "10px 16px",
  borderTop: "1px solid var(--border)",
};
