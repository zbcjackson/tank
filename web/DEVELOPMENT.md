# Web Frontend Development Guide

This document provides development commands and workflows for the Tank Web Frontend.

## Prerequisites

- Node.js 18+
- npm (bundled with Node)
- Tank Backend running on `localhost:8000`

## Setup

```bash
cd web
npm install
```

## Development

```bash
# Start dev server with HMR (opens on http://localhost:5173)
npm run dev

# Type-check without building
npx tsc --noEmit

# Lint
npm run lint
```

> The dev server proxies WebSocket connections to `localhost:8000` — make sure the backend is running first.

## Building

```bash
# Production build (output: dist/)
npm run build

# Preview production build locally
npm run preview
```

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
npx tsc --noEmit
```
