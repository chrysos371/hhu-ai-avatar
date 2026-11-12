import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
const assets = process.env.HHU_AVATAR_DATA_ROOT
  ?? execFileSync("python3", ["-B", resolve(__dirname, "../scripts/project_paths.py")], { encoding: "utf8" }).trim();
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // AudioWorklet modules must remain same-origin files under our strict CSP.
  build: { assetsInlineLimit: 0, outDir: resolve(assets, "frontend/dist"), emptyOutDir: true },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        configure(proxy) {
          proxy.on("proxyReq", (outgoing, request) => {
            if (request.headers.origin === "http://127.0.0.1:5173")
              outgoing.setHeader("Origin", "http://127.0.0.1:8765");
          });
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.tsx"],
  },
});
