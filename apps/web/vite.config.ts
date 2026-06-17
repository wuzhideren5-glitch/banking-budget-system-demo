import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const FRONTEND_PORT = 8443;
const BACKEND_PROXY_TARGET = process.env.VITE_BACKEND_PROXY_TARGET || "http://127.0.0.1:8009";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: FRONTEND_PORT,
    host: process.env.VITE_FRONTEND_HOST || "127.0.0.1",
    allowedHosts: ["guanheng.webank.com"],
    proxy: {
      "/api": { target: BACKEND_PROXY_TARGET, changeOrigin: true },
    },
  },
});
