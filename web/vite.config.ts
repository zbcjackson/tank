import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { viteStaticCopy } from 'vite-plugin-static-copy';
import basicSsl from '@vitejs/plugin-basic-ssl';

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    basicSsl(),
    react(),
    tailwindcss(),
    viteStaticCopy({
      targets: [
        {
          src: 'node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js',
          rename: { stripBase: true },
          dest: 'vad/',
        },
        {
          src: 'node_modules/@ricky0123/vad-web/dist/*.onnx',
          rename: { stripBase: true },
          dest: 'vad/',
        },
        {
          src: 'node_modules/onnxruntime-web/dist/*.wasm',
          rename: { stripBase: true },
          dest: 'ort/',
        },
        {
          src: 'node_modules/onnxruntime-web/dist/*.mjs',
          rename: { stripBase: true },
          dest: 'ort/',
        },
      ],
    }),
  ],
  server: {
    host: '0.0.0.0',
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
    // @tauri-apps/* packages are only loaded at runtime inside Tauri (dynamic import
    // guarded by __TAURI__). Exclude from the dep scanner so Vite doesn't warn
    // when running the plain web dev server where they're not installed.
    exclude: ['@tauri-apps/api', '@tauri-apps/plugin-http'],
  },
  build: {
    // WKWebView (Tauri) uses Safari's engine — target safari13 for compatibility
    target: process.env.TAURI_ENV_PLATFORM ? 'safari13' : undefined,
    rollupOptions: {
      // @tauri-apps/* are only available inside Tauri at runtime (dynamic import
      // guarded by __TAURI__). Externalize so Rollup doesn't fail on web builds.
      external: ['@tauri-apps/api/core', '@tauri-apps/api/event', '@tauri-apps/plugin-http'],
    },
  },
});
