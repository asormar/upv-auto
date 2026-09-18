import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // The Python adapter serves the API; `python -m upv_auto serve` runs it.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
