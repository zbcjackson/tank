import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { viteStaticCopy } from 'vite-plugin-static-copy';

// https://vite.dev/config/
export default defineConfig({
  plugins: [
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
  build: {
    // WKWebView (Tauri) uses Safari's engine — target safari13 for compatibility
    target: process.env.TAURI_ENV_PLATFORM ? 'safari13' : undefined,
  },
});
