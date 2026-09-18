import { stripVTControlCharacters } from 'node:util';
import { createLogger, defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { viteStaticCopy } from 'vite-plugin-static-copy';
import basicSsl from '@vitejs/plugin-basic-ssl';

const logger = createLogger();
const logError = logger.error.bind(logger);
logger.error = (message, options) => {
  const error = options?.error;
  // Browser teardown can reset a WS tunnel; retain every other proxy error.
  if (stripVTControlCharacters(message).startsWith('ws proxy ') && error &&
      'code' in error && error.code === 'ECONNRESET') return;
  logError(message, options);
};

// https://vite.dev/config/
export default defineConfig({
  customLogger: logger,
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
        // Tear down the tunnel on client FIN before buffered backend
        // frames can write to the ended TLS socket.
        configure: (proxy) => {
          proxy.on('proxyReqWs', (_proxyReq, _req, socket) => {
            socket.once('end', () => socket.destroy());
          });
        },
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
      external: [],
    },
  },
});
