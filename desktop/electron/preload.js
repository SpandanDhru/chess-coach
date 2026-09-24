"use strict";

const { contextBridge } = require("electron");

// The renderer only needs to know where the local API lives; everything else
// goes over plain HTTP. Expose a minimal, read-only surface.
const API_HOST = process.env.API_HOST || "127.0.0.1";
const API_PORT = Number(process.env.API_PORT || 8765);

contextBridge.exposeInMainWorld("chessCoach", {
  apiBase: `http://${API_HOST}:${API_PORT}`,
});
