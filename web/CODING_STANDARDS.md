# Web Frontend Coding Standards

This document defines coding standards for the Tank Web Frontend.

## Language & Style

- **TypeScript strict mode** — no `any` unless unavoidable; prefer `unknown` + type guards
- **Functional components only** — no class components
- **Named exports** for components; default export only for the root `App`
- **File naming**: `PascalCase` for components (`VoiceMode.tsx`), `camelCase` for hooks/services (`useAssistant.ts`)

## React Patterns

### Hooks

- Extract stateful logic into custom hooks (`use<Name>.ts` in `hooks/`)
- Keep components as thin presentational shells where possible
- Use `useCallback` for callbacks passed as props to avoid unnecessary re-renders
- Use `useRef` for mutable values that don't trigger re-renders (WebSocket client, AudioProcessor)

```tsx
// ✅ Good: logic in hook, component is thin
const { messages, sendMessage } = useAssistant(sessionId);
return <ChatMode messages={messages} onSendMessage={sendMessage} />;

// ❌ Bad: WebSocket logic inside component
function App() {
  const [ws, setWs] = useState<WebSocket | null>(null);
  useEffect(() => { /* 50 lines of ws setup */ }, []);
}
```

### State Updates

- Use functional updater form when new state depends on previous state

```tsx
// ✅ Good
setMessages(prev => [...prev, newMessage]);

// ❌ Bad (stale closure risk)
setMessages([...messages, newMessage]);
```

### Effects

- One concern per `useEffect`
- Always return a cleanup function when subscribing to external resources
- List all dependencies honestly — don't suppress the exhaustive-deps lint rule

```tsx
useEffect(() => {
  const client = new VoiceAssistantClient(sessionId);
  client.connect(handleMessage);
  return () => client.disconnect();
}, [sessionId, handleMessage]);
```

## TypeScript

### Type Definitions

- Define interfaces/types in the same file if used only there; move to a `types.ts` if shared
- Prefer `interface` for object shapes, `type` for unions/aliases

```ts
// ✅ Good: explicit types
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  type: StepType;
  content: string | ToolContent | WeatherContent;
}

// ❌ Bad: implicit any
const handleMessage = (msg) => { ... };
```

### Avoid `any`

```ts
// ✅ Good
const metadata: Record<string, unknown> = msg.metadata;

// ❌ Bad
const metadata: any = msg.metadata;
```

## Styling (Tailwind CSS)

- Use Tailwind utility classes directly in JSX — no separate CSS files except `index.css` for globals
- Use `clsx` / `tailwind-merge` for conditional class composition
- Keep class lists readable: group by concern (layout, spacing, color, typography)

```tsx
// ✅ Good: clsx for conditionals
<div className={clsx(
  "rounded-xl px-4 py-2",
  isUser ? "bg-blue-500 text-white" : "bg-slate-800 text-slate-100"
)} />

// ❌ Bad: string concatenation
<div className={"rounded-xl px-4 py-2 " + (isUser ? "bg-blue-500" : "bg-slate-800")} />
```

## Animation (Framer Motion)

- Use `AnimatePresence` for mount/unmount transitions
- Define `variants` objects outside the component to avoid recreation on each render
- Keep animations subtle — prefer `opacity` + `y` over complex transforms

```tsx
const variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0 },
};

<motion.div variants={variants} initial="hidden" animate="visible" />
```

## Services

- Services (`services/`) are plain TypeScript classes or functions — no React imports
- Side effects (WebSocket, AudioContext) live in services, not in components
- Services expose a clean interface; internal implementation details are private

## Error Handling

- Catch errors at the boundary where you can meaningfully handle them
- Show user-facing error states in the UI; log details to console
- Never swallow errors silently

```ts
// ✅ Good
audioProcessor.start().catch(err => {
  console.error("Failed to start audio:", err);
  setConnectionStatus('error');
});

// ❌ Bad
audioProcessor.start().catch(() => {});
```

## Imports

- Use path aliases if configured (`@/components/...`); otherwise use relative paths
- Keep imports grouped: React, third-party, local — separated by blank lines

```ts
import { useState, useEffect } from 'react';

import { motion } from 'framer-motion';

import { VoiceAssistantClient } from '../services/websocket';
import type { ChatMessage } from './types';
```
