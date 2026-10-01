import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev : http://localhost:5173 (origine autorisée par défaut dans ARGOS_ORIGINES_AUTORISEES).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, host: true },
});
