import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
    root: fileURLToPath(new URL(".", import.meta.url)),
    plugins: [react()],
    envDir: false,
    envPrefix: [],
    cacheDir: "../.local/tool-cache/vite",
    build: { outDir: "dist", sourcemap: false, target: "es2022" },
    test: {
        environment: "jsdom",
        setupFiles: ["./src/test/setup.ts"],
        environmentOptions: { jsdom: { url: "https://localhost:8443/" } },
        clearMocks: true,
        restoreMocks: true,
        maxWorkers: 2,
    },
});
