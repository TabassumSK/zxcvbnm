import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, forward /api requests to the Python backend.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});