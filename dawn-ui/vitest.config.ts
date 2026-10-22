import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  // Match the app's JSX transform (Next.js uses the automatic runtime), so
  // components don't need `import React` in scope under vitest's esbuild.
  esbuild: {
    jsx: "automatic",
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  test: {
    environment: "node",
  },
});
