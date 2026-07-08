import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const webPort = Number(process.env.PRIVLEDGER_WEB_PORT ?? "5173");
const apiTarget =
  process.env.PRIVLEDGER_API_URL ??
  `http://127.0.0.1:${process.env.PRIVLEDGER_API_PORT ?? "4577"}`;

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: webPort,
    proxy: {
      "/api": apiTarget,
    },
  },
  preview: {
    host: "127.0.0.1",
    port: webPort,
    proxy: {
      "/api": apiTarget,
    },
  },
});
