import React from "react";
import { Chessboard } from "react-chessboard";
import { START_FEN } from "../lib/fen.js";

// Board display using react-chessboard's imported piece set, driven by a FEN.
// Beige/brown squares to match the retro theme; pieces are not draggable (this
// is a review board, not a play board).
export default function Board({ fen = START_FEN, width = 456, orientation = "white" }) {
  return (
    <div
      style={{
        width,
        border: "2px solid var(--border)",
        boxShadow: "0 0 0 2px #000, 0 0 24px rgba(224,164,88,0.08)",
      }}
    >
      <Chessboard
        id="review-board"
        position={fen}
        boardWidth={width}
        boardOrientation={orientation}
        arePiecesDraggable={false}
        customLightSquareStyle={{ backgroundColor: "#e8d2a6" }}
        customDarkSquareStyle={{ backgroundColor: "#9c6b3f" }}
        customBoardStyle={{ borderRadius: 0 }}
      />
    </div>
  );
}
