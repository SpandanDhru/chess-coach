import React from "react";

// Inline piece icon for coach *text* (the board uses react-chessboard's set).
// Uses the font's filled chess glyphs, tinted so white vs black pieces stay
// distinguishable on the dark terminal background.
const GLYPH = { K: "♚", Q: "♛", R: "♜", B: "♝", N: "♞", P: "♟" };

export default function PieceIcon({ code, size = 18, inline = true }) {
  if (!code || code.length < 2) return null;
  const glyph = GLYPH[code[1].toUpperCase()];
  if (!glyph) return null;
  const isWhite = code[0] === "w";

  return (
    <span
      aria-label={code}
      title={code}
      style={{
        fontSize: size,
        lineHeight: 1,
        color: isWhite ? "#f2e6c8" : "#c88f45",
        textShadow: isWhite
          ? "0 0 1px #000, 0 0 2px #000"
          : "0 0 1px #000, 0 0 2px #000",
        margin: inline ? "0 2px" : 0,
        verticalAlign: "-0.15em",
        fontFamily: "'DejaVu Sans', 'Segoe UI Symbol', sans-serif",
      }}
    >
      {glyph}
    </span>
  );
}
