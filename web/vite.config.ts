import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// En desarrollo, /api va a la API local (uvicorn en el 8000): mismo origen, sin CORS.
const api = process.env.API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: api, changeOrigin: true, rewrite: (path) => path.replace(/^\/api/, "") } },
  },
  test: { environment: "jsdom", globals: false },
});
