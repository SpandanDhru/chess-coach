import React, { useEffect, useMemo, useRef, useState } from "react";
import Board from "./Board.jsx";
import { api } from "../lib/api.js";
import { renderPieces } from "../lib/renderPieces.jsx";
import { START_FEN } from "../lib/fen.js";

const CLS_COLOR = {
  blunder: "var(--danger)",
  mistake: "#e08a3c",
  inaccuracy: "#d8c24a",
  best: "var(--accent-2)",
  good: "var(--text)",
};

// Index of the single worst move, so review opens on the key moment.
function keyIndex(moves) {
  let best = 0;
  let worst = -1;
  moves.forEach((m, i) => {
    const cp = m.centipawn_loss || 0;
    if (cp > worst) {
      worst = cp;
      best = i;
    }
  });
  return moves.length ? best : 0;
}

export default function ReviewPanel({ review }) {
  const moves = review?.moves || [];
  const [ply, setPly] = useState(0);
  const [explanations, setExplanations] = useState({}); // position_id -> text
  const [busy, setBusy] = useState(false);
  const listRef = useRef(null);

  // Reset when a new game is loaded; seed cached explanations from the payload.
  useEffect(() => {
    if (!review) return;
    setPly(keyIndex(review.moves || []));
    const seed = {};
    (review.moves || []).forEach((m) => {
      if (m.explanation) seed[m.position_id] = m.explanation;
    });
    setExplanations(seed);
  }, [review?.game_id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the active move visible in the list.
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-ply="${ply}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [ply]);

  const current = moves[ply];
  const fen = current ? current.fen : START_FEN;
  const orientation = review?.color === "black" ? "black" : "white";

  const currentExplanation = current
    ? explanations[current.position_id]
    : undefined;

  async function explain() {
    if (!current?.position_id || busy) return;
    if (explanations[current.position_id]) return;
    setBusy(true);
    try {
      const { explanation } = await api.explainPosition(current.position_id);
      setExplanations((e) => ({ ...e, [current.position_id]: explanation }));
    } catch (err) {
      setExplanations((e) => ({
        ...e,
        [current.position_id]: `! ${err.message}`,
      }));
    } finally {
      setBusy(false);
    }
  }

  const caption = useMemo(() => {
    if (!review) return "starting position";
    if (!current) return review.game_id;
    return `game ${review.game_id} · ${review.opening || "?"}`;
  }, [review, current]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <Board fen={fen} orientation={orientation} />
      <div className="dim" style={{ fontSize: 12, textAlign: "center" }}>
        {caption}
      </div>

      {!review && (
        <div className="dim" style={{ fontSize: 12, textAlign: "center", maxWidth: 456 }}>
          type <span className="accent">games</span> in the chat and click one to
          step through it here.
        </div>
      )}

      {review && current && (
        <>
          <div style={navRow}>
            <button onClick={() => setPly(0)} disabled={ply === 0}>
              |&lt;
            </button>
            <button onClick={() => setPly((p) => Math.max(0, p - 1))} disabled={ply === 0}>
              &lt; prev
            </button>
            <span style={{ flex: 1, textAlign: "center" }} className="dim">
              move {ply + 1}/{moves.length}
            </span>
            <button
              onClick={() => setPly((p) => Math.min(moves.length - 1, p + 1))}
              disabled={ply >= moves.length - 1}
            >
              next &gt;
            </button>
            <button
              onClick={() => setPly(moves.length - 1)}
              disabled={ply >= moves.length - 1}
            >
              &gt;|
            </button>
          </div>

          <div className="panel" style={{ padding: 10, fontSize: 13 }}>
            <div>
              <span className="dim">{current.move_number}.</span>{" "}
              <span style={{ color: CLS_COLOR[current.classification] || "var(--text)" }}>
                {current.san}
              </span>{" "}
              <span className="dim">({current.classification || "—"}</span>
              {current.centipawn_loss != null && (
                <span className="dim">, -{Math.round(current.centipawn_loss)}cp</span>
              )}
              <span className="dim">)</span>
              {current.best_move_san && current.best_move_san !== current.san && (
                <span className="dim"> · best: {current.best_move_san}</span>
              )}
            </div>

            <div style={{ marginTop: 8 }}>
              {currentExplanation ? (
                <div style={{ whiteSpace: "pre-wrap" }}>
                  {renderPieces(currentExplanation)}
                </div>
              ) : (
                <button onClick={explain} disabled={busy}>
                  {busy ? "thinking..." : "▸ explain this move"}
                </button>
              )}
            </div>
          </div>

          <div ref={listRef} style={moveList} className="panel">
            {moves.map((m, i) => (
              <span
                key={i}
                data-ply={i}
                onClick={() => setPly(i)}
                style={{
                  cursor: "pointer",
                  padding: "1px 4px",
                  background: i === ply ? "var(--sq-mark)" : "transparent",
                  color: CLS_COLOR[m.classification] || "var(--text)",
                }}
              >
                {i % 2 === 0 ? `${m.move_number}.` : ""}
                {m.san}
                {m.is_blunder ? "??" : ""}{" "}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

const navRow = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  width: 456,
};
const moveList = {
  width: 456,
  maxHeight: 96,
  overflowY: "auto",
  padding: 8,
  fontSize: 12,
  lineHeight: 1.7,
};
