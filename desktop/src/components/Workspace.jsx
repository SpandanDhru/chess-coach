import React, { useState } from "react";
import ReviewPanel from "./ReviewPanel.jsx";
import Terminal from "./Terminal.jsx";
import { api } from "../lib/api.js";

export default function Workspace({ username, platform, onExit }) {
  const [review, setReview] = useState(null);
  const [loadError, setLoadError] = useState(null);

  async function loadBoard(gameId) {
    setLoadError(null);
    try {
      const data = await api.getReview(gameId);
      setReview(data);
    } catch (e) {
      setLoadError(e.message);
    }
  }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <header style={headerStyle}>
        <div>
          <span className="accent">chess coach</span>
          <span className="dim">
            {" "}
            // {platform} :: {username}
          </span>
        </div>
        <button onClick={onExit} title="enter a different username">
          ⌂ home
        </button>
      </header>
      <div style={bodyStyle}>
        <div style={leftStyle}>
          <ReviewPanel review={review} />
          {loadError && (
            <div className="danger" style={{ fontSize: 12 }}>
              ! {loadError}
            </div>
          )}
        </div>
        <div style={rightStyle}>
          <Terminal username={username} onLoadBoard={loadBoard} />
        </div>
      </div>
    </div>
  );
}

const headerStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "8px 16px",
  borderBottom: "1px solid var(--border)",
  fontSize: 13,
  letterSpacing: 1,
};
const bodyStyle = {
  flex: 1,
  display: "flex",
  gap: 16,
  padding: 16,
  minHeight: 0,
};
const leftStyle = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: 8,
  paddingTop: 4,
};
const rightStyle = { flex: 1, minWidth: 0 };
