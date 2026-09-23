import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // GitHub Pages serves this project under a path (e.g. `/upv-auto/`), so
  // every built asset URL must resolve under it (platform-operations spec:
  // GitHub Pages Hosting). Local dev and `serve --demo` never set
  // `VITE_BASE_PATH`, so this stays `/` there and the `/api` proxy below is
  // unaffected.
  base: process.env.VITE_BASE_PATH ?? "/",
  plugins: [react()],
  server: {
    // The Python adapter serves the API; `python -m upv_auto serve` runs it.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
