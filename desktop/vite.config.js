import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" so built asset paths are relative and load under Electron's
// file:// protocol in the packaged app.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
