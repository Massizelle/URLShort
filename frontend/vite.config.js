import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/api/shorten": { target: "http://localhost:8000", changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/shorten/, "") },
      "/api/analytics": { target: "http://localhost:8001", changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/analytics/, "") },
    },
  },
});
