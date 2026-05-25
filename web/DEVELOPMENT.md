# Web Frontend Development Guide

This document provides development commands and workflows for the Tank Web Frontend.

## Prerequisites

- Node.js 18+
- pnpm
- Tank Backend running on `localhost:8000`

## Setup

```bash
cd web
pnpm install
```

## Development

```bash
# Start dev server with HMR (opens on http://localhost:5173)
pnpm dev

# Type-check without building (must use -b to follow project references)
npx tsc -b --noEmit

# Lint
pnpm lint
```

> The dev server proxies WebSocket connections to `localhost:8000` — make sure the backend is running first.

## Building

```bash
# Production build (output: dist/)
pnpm build

# Preview production build locally
pnpm preview
```

## Production Deployment

For production, Tank runs behind nginx as a single‑origin gateway. The SPA,
REST API, and WebSocket all share one public HTTPS host — no CORS, no mixed
content.

### Quick Start

1. Build the frontend: `pnpm build` → produces `dist/`.
2. Copy `dist/*` to `/srv/tank/web/` on your server.
3. Install nginx and copy `deploy/nginx.conf` to `/etc/nginx/sites-available/tank`.
4. Edit `server_name` and SSL paths in the nginx config.
5. `ln -s /etc/nginx/sites-available/tank /etc/nginx/sites-enabled/`
6. `nginx -t && nginx -s reload`

### nginx Configuration

A ready‑to‑use nginx config lives at `deploy/nginx.conf` in the repo. It:

- Serves the SPA from `/srv/tank/web/` with cache headers.
- Proxies `/api/*` to `http://127.0.0.1:8000` (backend).
- Proxies `/ws/*` with WebSocket upgrade, long timeouts, and buffering off.
- Enforces HTTPS with optional HTTP→HTTPS redirect.

### SSL Certificates

Use Let's Encrypt with certbot, or provide your own certificates:

```bash
certbot certonly --webroot -w /var/www/html -d tank.example.com
ln -s /etc/letsencrypt/live/tank.example.com/fullchain.pem /etc/ssl/tank/
ln -s /etc/letsencrypt/live/tank.example.com/privkey.pem /etc/ssl/tank/
```

Then update `ssl_certificate` and `ssl_certificate_key` in `nginx.conf`.

### Backend Requirements

- Backend must be running on `127.0.0.1:8000` (or update `proxy_pass`).
- No CORS middleware needed — nginx makes all requests same‑origin.
- For file uploads, `client_max_body_size` in nginx must match or exceed the backend's upload size limit (50MB in the template).

### Tauri Considerations

Tauri bundles the `dist/` files directly into the `.app`, so it doesn't go through nginx. For REST requests under Tauri, `@tauri-apps/plugin-http` is used to bypass browser CORS entirely. This means:
- Browser users → nginx gateway → backend (single origin)
- Tauri users → plugin-http → backend (direct, no CORS)

Both work without CORS headers on the backend.

## Testing

> Tests are not yet set up. See [TESTING.md](TESTING.md) for setup instructions.

```bash
# Once Vitest is configured:
npx vitest run          # Single run (CI-friendly)
npx vitest              # Watch mode
npx vitest --coverage   # With coverage
```

## Common Tasks

### Add a New Component

1. Create `src/components/<Name>.tsx`
2. Export a named function component
3. Add Tailwind classes for styling
4. Import and use in parent component

### Add a New Hook

1. Create `src/hooks/use<Name>.ts`
2. Keep all side effects inside `useEffect` with proper cleanup
3. Return only what consumers need

### Change Backend URL

The backend URL defaults to `localhost:8000`. To point at a different server, edit `VoiceAssistantClient` constructor call in `hooks/useAssistant.ts` or expose it as a config constant.

### Add a New Message Type

1. Add the new type to `MessageType` in `services/websocket.ts`
2. Handle it in `handleMessage` inside `hooks/useAssistant.ts`
3. Add a renderer in `components/Assistant/MessageStep.tsx`

## Troubleshooting

### Blank page / no connection

- Verify backend is running: `curl http://localhost:8000/health`
- Check browser console for WebSocket errors
- Ensure microphone permission is granted

### Audio not playing

- Check browser console for AudioContext errors
- Some browsers require a user gesture before AudioContext can start
- Try clicking anywhere on the page first

### TypeScript errors

```bash
npx tsc -b --noEmit
```
