import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    watch: { ignored: ['**/src-tauri/**'] },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  optimizeDeps: {
    // onnxruntime-web uses WASM + worker files that break under Vite's dep optimizer.
    // Excluding it lets the browser resolve the .wasm/.mjs files directly.
    exclude: ['onnxruntime-web'],
  },
  build: {
    // WKWebView (Tauri) uses Safari's engine — target safari13 for compatibility
    target: process.env.TAURI_ENV_PLATFORM ? 'safari13' : undefined,
  },
});
